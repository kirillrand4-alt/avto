# -*- coding: utf-8 -*-
"""Заслон «сделка в работе» ПО НАПРАВЛЕНИЯМ (владелец 14.10).

Правило владельца:
  * у компании идёт сделка Meyer — не пишет ТОЛЬКО Meyer (КЦ писать может);
  * идёт сделка КЦ — не пишет только КЦ (Meyer писать может);
  * сделка только в СЦ (сервисный центр) — писать могут все.
Считаются только АКТИВНЫЕ сделки («В работе»). Воронки: MEYER-* → meyer,
КЦ-* и «Общая воронка» → kc, всё с «СЦ» (в т.ч. MEYER-СЦ) → sc.

Таблица sender.db/sdelki_napr(inn, meyer, kc, sc, detali, ts) — заливается
из выгрузки Битрикса (ops/sdelki_napr_zaliv.py). Модуль только читает.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

СХЕМА = """
CREATE TABLE IF NOT EXISTS sdelki_napr (
    inn    TEXT PRIMARY KEY,
    meyer  INTEGER NOT NULL DEFAULT 0,
    kc     INTEGER NOT NULL DEFAULT 0,
    sc     INTEGER NOT NULL DEFAULT 0,
    detali TEXT,
    ts     TEXT NOT NULL
)"""

_ИМЯ = {"meyer": "Meyer", "kc": "КЦ"}


def _цифры(inn) -> str:
    return "".join(c for c in str(inn or "") if c.isdigit())


def blok(conn: sqlite3.Connection, inn, division: Optional[str]) -> Optional[str]:
    """Причина запрета письма направления division этой компании или None."""
    if division not in ("meyer", "kc"):
        return None
    ц = _цифры(inn)
    if not ц:
        return None
    try:
        р = conn.execute("SELECT meyer, kc FROM sdelki_napr WHERE inn=?", (ц,)).fetchone()
    except sqlite3.Error:
        return None          # таблицы ещё нет — заслон молчит, а не роняет отправку
    if not р:
        return None
    if (р[0] if division == "meyer" else р[1]):
        return "сделка %s в работе (Битрикс): %s не пишет" % (_ИМЯ[division], _ИМЯ[division])
    return None
