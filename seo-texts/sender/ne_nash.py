# -*- coding: utf-8 -*-
"""Реестр «не наш адресат»: компании, которым не пишем никогда.

Зачем отдельная таблица, а не статус карточки. Снятая карточка убирает
ПИСЬМО, но не КОМПАНИЮ: пул кандидатов её не помнит, и на следующем
прогоне она приходит снова. 20.08 ООО «ВОЗДУХ» сгенерировалось трижды за
день по $0.6 — я снимал его утром вручную («сами производят технические
газы»), потом оно вернулось пересудом гейта, потом пришло опять.

Что сюда попадает — только РЕШЕНИЯ, которые не зависят от модели:
  * сайт показывает другое занятие (магазин вместо производства);
  * компания сама производит то, что мы продаём;
  * отрасль вне канона направления (напитки у Мейера);
  * прямое указание владельца.

Что сюда НЕ попадает: вердикты линз и гейта. Замер 20.08 показал, что
один и тот же гейт на одних данных в двух прогонах подряд даёт разные
ответы — такому вечности доверять нельзя.

Хранение durable и в двух базах, как приговоры доставки: sender.db —
для панели и генерации, enrich.db — для отбора кандидатов. Сбой второй
записи не отменяет первую.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

СХЕМА = """
CREATE TABLE IF NOT EXISTS ne_nash_adresat (
    inn      TEXT PRIMARY KEY,
    prichina TEXT NOT NULL,
    kto      TEXT NOT NULL,
    ts       TEXT NOT NULL
)"""


def _цифры(inn) -> str:
    return "".join(c for c in str(inn or "") if c.isdigit())


def _создать(conn) -> None:
    # ЖДЁМ ЗАМОК. Базу делят панель, авто-отправка и разовые прогоны; 26.08
    # запись конкурента в реестр упала с «database is locked» ровно потому,
    # что рядом шёл разбор очереди. Реестр — решение оператора, терять его
    # из-за чужой транзакции нельзя.
    try:
        conn.execute("PRAGMA busy_timeout=60000")
    except sqlite3.Error:                                     # noqa: BLE001
        pass
    conn.execute(СХЕМА)


class НеНаш:
    """Реестр «не наш адресат» поверх sqlite. Зеркало — по желанию."""

    def __init__(self, путь: str, зеркало: Optional[str] = None):
        self.путь = str(путь)
        self.зеркало = str(зеркало) if зеркало else ""
        with sqlite3.connect(self.путь, timeout=30) as c:
            _создать(c)

    # -- запись ------------------------------------------------------------ #

    def записать(self, inn, причина: str, кто: str) -> bool:
        """Внести компанию. Повторная запись обновляет причину, не плодит строк."""
        инн = _цифры(inn)
        if not инн:
            return False
        сейчас = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.путь, timeout=30) as c:
            _создать(c)
            c.execute(
                "INSERT INTO ne_nash_adresat (inn, prichina, kto, ts) "
                "VALUES (?,?,?,?) ON CONFLICT(inn) DO UPDATE SET "
                "prichina=excluded.prichina, kto=excluded.kto, ts=excluded.ts",
                (инн, str(причина)[:400], str(кто)[:120], сейчас))
        # Зеркало в обогащение: его читает отбор кандидатов, и он живёт
        # отдельно от панели. Сбой зеркала не отменяет основную запись —
        # иначе недоступность одной базы роняла бы решение оператора.
        if self.зеркало:
            try:
                with sqlite3.connect(self.зеркало, timeout=30) as c:
                    _создать(c)
                    c.execute(
                        "INSERT INTO ne_nash_adresat (inn, prichina, kto, ts) "
                        "VALUES (?,?,?,?) ON CONFLICT(inn) DO UPDATE SET "
                        "prichina=excluded.prichina, kto=excluded.kto, "
                        "ts=excluded.ts",
                        (инн, str(причина)[:400], str(кто)[:120], сейчас))
            except Exception:                                    # noqa: BLE001
                pass
        return True

    def убрать(self, inn) -> bool:
        """Вернуть компанию в работу: решение человека бывает ошибочным."""
        инн = _цифры(inn)
        if not инн:
            return False
        with sqlite3.connect(self.путь, timeout=30) as c:
            _создать(c)
            c.execute("DELETE FROM ne_nash_adresat WHERE inn=?", (инн,))
        if self.зеркало:
            try:
                with sqlite3.connect(self.зеркало, timeout=30) as c:
                    _создать(c)
                    c.execute("DELETE FROM ne_nash_adresat WHERE inn=?", (инн,))
            except Exception:                                    # noqa: BLE001
                pass
        return True

    # -- чтение ------------------------------------------------------------ #

    def есть(self, inn) -> bool:
        инн = _цифры(inn)
        if not инн:
            return False
        with sqlite3.connect(self.путь, timeout=30) as c:
            _создать(c)
            return c.execute("SELECT 1 FROM ne_nash_adresat WHERE inn=?",
                             (инн,)).fetchone() is not None

    def набор(self, инны: Optional[Iterable] = None) -> set:
        """Множество ИНН из реестра. Чтение оптом — один запрос на партию."""
        with sqlite3.connect(self.путь, timeout=30) as c:
            _создать(c)
            if инны is None:
                return {str(r[0]) for r in
                        c.execute("SELECT inn FROM ne_nash_adresat")}
            свои = [_цифры(i) for i in инны]
            свои = [i for i in свои if i]
            если_нет = set()
            for i in range(0, len(свои), 400):
                кусок = свои[i:i + 400]
                зн = ",".join("?" * len(кусок))
                если_нет |= {str(r[0]) for r in c.execute(
                    f"SELECT inn FROM ne_nash_adresat WHERE inn IN ({зн})",
                    tuple(кусок))}
            return если_нет

    def причина(self, inn) -> str:
        инн = _цифры(inn)
        with sqlite3.connect(self.путь, timeout=30) as c:
            _создать(c)
            r = c.execute("SELECT prichina FROM ne_nash_adresat WHERE inn=?",
                          (инн,)).fetchone()
        return str(r[0]) if r else ""


def build_ne_nash(sender_db: str = r"C:\sender\sender.db",
                  enrich_db: str = r"C:\sender\enrich.db") -> "НеНаш":
    return НеНаш(sender_db, enrich_db)
