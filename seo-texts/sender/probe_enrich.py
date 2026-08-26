# -*- coding: utf-8 -*-
"""Вердикт проверки адреса — обратно в базу обогащения.

Вопрос владельца 12.08: «а почты убираются в принципе из всех баз?». Ответ был
«нет»: мёртвый адрес попадал в стоп-лист панели, письмо снималось, но в
enrich.db он продолжал лежать как обычный контакт. У snab@volga-ice.ru, про
который сервер прямо сказал «нет такого ящика», в обогащении стояло mx_ok=1 и
роль «снабжение/закупки» — то есть он выглядел хорошим контактом.

Чем это плохо. Стоп-лист панели — надёжный ПОСЛЕДНИЙ рубеж, письмо не уйдёт.
Но отбор кандидатов делается из enrich.db, и мёртвые всплывают в нём снова:
занимают места в очередях, тратят генерацию (минуты провайдерского времени и
деньги на письмо), съедают дневную квоту. 12.08 так и вышло: snab@volga-ice.ru
попал в отбор Meyer, ему сгенерировали письмо, и снял его только заслон.

Здесь вердикт доезжает до обогащения, чтобы адрес выпадал из работы ОДИН РАЗ,
а не ловился на последнем рубеже каждый раз заново.

Пишем в свои колонки (probe_verdict, probe_ts, probe_answer), а не в чужие
mx_ok/addr_class: их заполняет обогащение своим смыслом, и затирать его
вердиктом пробы нельзя — потеряем сведения о том, откуда взялся адрес.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Вердикты, которые означают «сюда писать нельзя». Остальные (есть, принимает
# всё, неясно, отказ пробе) — не приговор и записываются просто как факт.
СМЕРТЕЛЬНЫЕ = ("нет ящика", "нет MX")


def найти(config: object, db_path: str = "") -> Optional[str]:
    """Где лежит база обогащения. Настройка, иначе — рядом с базой панели.

    На сервере это `C:\\sender\\enrich.db` рядом с `sender.db`; на чужой машине
    и в тестах её нет — тогда None, и запись вердиктов молча выключается.
    """
    путь = ""
    try:
        путь = str(config.get("service.enrich_db", "") or "")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        путь = ""
    if путь:
        return путь
    if db_path:
        рядом = os.path.join(os.path.dirname(os.path.abspath(str(db_path))),
                             "enrich.db")
        if os.path.exists(рядом):
            return рядом
    return None


def _подготовить(con: sqlite3.Connection) -> None:
    """Свои колонки для вердикта. Старая база без них — не ошибка."""
    for имя, тип in (("probe_verdict", "TEXT"), ("probe_ts", "TEXT"),
                     ("probe_answer", "TEXT")):
        try:
            con.execute(f"ALTER TABLE emails ADD COLUMN {имя} {тип}")
        except sqlite3.OperationalError:
            pass                        # колонка уже есть
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_emails_probe "
                    "ON emails(probe_verdict)")
    except sqlite3.OperationalError:
        pass


def записать(enrich_db: Optional[str], вердикты: Iterable[dict]) -> dict:
    """Проставить вердикты в enrich.db. Возвращает сводку.

    вердикты: [{email, verdict, answer}]. Молча выходим, если базы нет: панель
    обязана работать и без обогащения (тесты, чужая машина).
    """
    итог = {"обновлено": 0, "смертельных": 0, "пропущено": 0}
    if not enrich_db or not os.path.exists(enrich_db):
        return итог
    строки = [з for з in вердикты if (з or {}).get("email")]
    if not строки:
        return итог
    сейчас = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        con = sqlite3.connect(enrich_db, timeout=30)
    except sqlite3.Error:
        logger.exception("probe_enrich: не открылась база обогащения")
        return итог
    try:
        # ЖДЁМ ЗАМОК, А НЕ ПАДАЕМ. В enrich.db одновременно пишет обогащение
        # (свой воркер держит запись пачками), и приём вердиктов приходился
        # ровно на его окно. 26.08 разбор показал цену: 5024 приговора
        # «мёртв» так и не доехали до обогащения, потому что ПЕРВЫЙ же
        # UPDATE получил «database is locked», внешний except проглотил
        # ошибку — и вся пачка молча вернулась нулями.
        con.execute("PRAGMA busy_timeout=60000")
    except sqlite3.Error:                     # noqa: BLE001 - не критично
        pass
    try:
        _подготовить(con)
        for з in строки:
            адрес = str(з.get("email") or "").strip().lower()
            вердикт = str(з.get("verdict") or "").strip()
            if not адрес or not вердикт:
                итог["пропущено"] += 1
                continue
            # ОДНА СТРОКА НЕ ХОРОНИТ ПАЧКУ. Замок отпускают через секунды,
            # поэтому повторяем, а на упорный сбой считаем строку и идём
            # дальше: вердикты остальных важнее.
            for попытка in range(3):
                try:
                    cur = con.execute(
                        "UPDATE emails SET probe_verdict=?, probe_ts=?, "
                        "probe_answer=? WHERE lower(email)=?",
                        (вердикт, сейчас,
                         str(з.get("answer") or "")[:200], адрес))
                except sqlite3.Error:
                    if попытка == 2:
                        итог["не_легло"] = итог.get("не_легло", 0) + 1
                        break
                    time.sleep(1.5 * (попытка + 1))
                    continue
                if cur.rowcount:
                    итог["обновлено"] += cur.rowcount
                    if вердикт in СМЕРТЕЛЬНЫЕ:
                        итог["смертельных"] += cur.rowcount
                break
        con.commit()
    except sqlite3.Error:
        logger.exception("probe_enrich: вердикты не записались")
    finally:
        con.close()
    return итог


def zhivye_tolko(enrich_db: Optional[str], адреса: Iterable[str]) -> set:
    """Отфильтровать заведомо недоставимые. Для отборов кандидатов.

    Возвращает множество адресов, которым писать МОЖНО. Нет базы или колонки —
    возвращаем всё: отбор не должен пустеть из-за отсутствия проверки.
    """
    сп = [str(a).strip().lower() for a in адреса if a and "@" in str(a)]
    if not сп or not enrich_db or not os.path.exists(enrich_db):
        return set(сп)
    мёртвые: set = set()
    try:
        con = sqlite3.connect(f"file:{enrich_db}?mode=ro", uri=True, timeout=30)
        try:
            for i in range(0, len(сп), 500):
                кусок = сп[i:i + 500]
                q = ("SELECT lower(email) FROM emails WHERE probe_verdict IN "
                     "(%s) AND lower(email) IN (%s)"
                     % (",".join("?" * len(СМЕРТЕЛЬНЫЕ)),
                        ",".join("?" * len(кусок))))
                for (a,) in con.execute(q, (*СМЕРТЕЛЬНЫЕ, *кусок)):
                    мёртвые.add(a)
        finally:
            con.close()
    except sqlite3.Error:
        return set(сп)                  # колонки ещё нет — фильтровать нечем
    return {a for a in сп if a not in мёртвые}
