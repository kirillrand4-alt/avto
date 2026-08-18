# -*- coding: utf-8 -*-
"""Жёсткая отбивка — приговор адресу, и он обязан осесть во всех трёх базах.

Правило владельца (CLAUDE.md): мёртвый адрес выпадает из работы ОДИН раз и
навсегда, а не ловится на последнем рубеже каждый раз заново. У каждой базы
своя роль:

  sender.db/addr_probe            — кэш панели: заслон подтверждения и фильтр
                                    списка «кому»;
  enrich.db/emails.probe_verdict  — обогащение: отбор кандидатов в генерацию;
  obzvon-index.db/email_probe     — база обзвона на 161к.

Замер 18.08 показал, что отбивка доезжала только до стоп-листа: из девяти
адресов с жёсткой отбивкой вердикт пробы был обновлён у одного, а три письма
всё ещё висели approved. Хуже того, у kk@vebfabrika.ru работник проб в 04:45
поставил «есть» (код 250 — домен принимает любой адрес) ПОВЕРХ нашего «нет
ящика», и адрес вернулся в работу.

Отсюда пометка источника: вердикт доставки пишется как `hard-bounce`, и
AddrProbe._save такую запись пробе перебить не даёт. Разница по существу:
проба ЗАДАЁТ ВОПРОС и её обманывает catch-all, а доставка ПОЛУЧАЕТ ОТВЕТ на
реально отправленное письмо.

Приговор — только жёсткая отбивка (verdict=hard в DSN). Отказ по политике
(«blocked due to security reason», 5.7.x) сюда не попадает: там ящик живой,
завернули письмо.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

ИСТОЧНИК = "hard-bounce"
ВЕРДИКТ = "нет ящика"

_ОБЗВОН_ТАБЛИЦА = """
CREATE TABLE IF NOT EXISTS email_probe (
    email   TEXT PRIMARY KEY,
    verdict TEXT,
    source  TEXT,
    answer  TEXT,
    ts      TEXT
)"""


def _путь_обзвона(config: Any) -> str:
    try:
        return str(config.get("obzvon.index_path", "") or "")
    except Exception:  # noqa: BLE001
        return ""


def _в_обзвон(путь: str, адреса: list, диагностика: str, сейчас: str) -> int:
    if not путь or not os.path.exists(путь):
        return 0
    сколько = 0
    try:
        con = sqlite3.connect(путь, timeout=20)
        try:
            con.execute(_ОБЗВОН_ТАБЛИЦА)
            for а in адреса:
                con.execute(
                    "INSERT INTO email_probe (email,verdict,source,answer,ts) "
                    "VALUES (?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                    "verdict=excluded.verdict, source=excluded.source, "
                    "answer=excluded.answer, ts=excluded.ts",
                    (а, ВЕРДИКТ, ИСТОЧНИК, диагностика[:200], сейчас))
                сколько += 1
            con.commit()
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        logger.exception("отбивка: не записалась в базу обзвона")
    return сколько


def zapisat(адреса: Iterable[str], диагностика: str = "", *,
            db_path: str = "", config: Any = None,
            enrich_db: Optional[str] = None,
            obzvon_db: Optional[str] = None) -> dict:
    """Разнести приговор доставки по трём базам. Возвращает сводку.

    Ни одна база не обязана существовать: панель работает и без обогащения
    (тесты, чужая машина), а сбой одной записи не отменяет остальные —
    письмо уже отбилось, терять вердикт целиком нельзя.
    """
    список = sorted({(а or "").strip().lower() for а in адреса if (а or "").strip()})
    итог = {"адресов": len(список), "addr_probe": 0, "enrich": 0, "obzvon": 0}
    if not список:
        return итог
    текст = f"жёсткая отбивка: {диагностика}".strip()[:200]
    сейчас = datetime.now(timezone.utc).isoformat()

    if db_path:
        try:
            from sender.addr_probe import AddrProbe
            п = AddrProbe(db_path)
            for а in список:
                if п.prigovor_dostavki(а, ВЕРДИКТ, текст, 550):
                    итог["addr_probe"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("отбивка: вердикт не доехал до кэша проб")

    путь_обогащения = enrich_db
    if путь_обогащения is None and config is not None:
        try:
            from sender.probe_enrich import найти
            путь_обогащения = найти(config, db_path)
        except Exception:  # noqa: BLE001
            путь_обогащения = None
    if путь_обогащения:
        try:
            from sender.probe_enrich import записать
            р = записать(путь_обогащения,
                         [{"email": а, "verdict": ВЕРДИКТ, "answer": текст}
                          for а in список])
            итог["enrich"] = int(р.get("обновлено") or 0)
        except Exception:  # noqa: BLE001
            logger.exception("отбивка: вердикт не доехал до обогащения")

    путь_обзвона = obzvon_db
    if путь_обзвона is None:
        путь_обзвона = _путь_обзвона(config) if config is not None else ""
    итог["obzvon"] = _в_обзвон(путь_обзвона or "", список, текст, сейчас)
    return итог
