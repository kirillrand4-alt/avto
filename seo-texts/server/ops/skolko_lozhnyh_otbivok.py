# -*- coding: utf-8 -*-
"""Сколько событий-отбивок на самом деле не отбивки.

Признак тот же, что теперь стоит заслоном: в разборе пусто - нет адресов
недоставки, нет кода SMTP, нет расширенного статуса. Такие события
попали в счётчик недоставки зря.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT id, event_ts, message_id, detail_json FROM events "
    " WHERE event_type IN ('bounce','dsn') ORDER BY id").fetchall()
пустых, всего = [], 0
причины = Counter()
for р in строки:
    всего += 1
    try:
        д = json.loads(р["detail_json"] or "{}")
    except Exception:                                          # noqa: BLE001
        continue
    dsn = д.get("dsn") or {}
    if not (dsn.get("failed") or dsn.get("smtp_code") or dsn.get("status")):
        пустых.append(р)
        причины[str(dsn.get("verdict") or "?")] += 1

print(f"событий недоставки всего: {всего}")
print(f"из них с ПУСТЫМ разбором: {len(пустых)}")
print(f"вердикты пустых: {dict(причины)}")
print("\nпоследние такие:")
for р in пустых[-8:]:
    д = json.loads(р["detail_json"] or "{}")
    отпр = (д.get("headers") or {}).get("From", "")[:46]
    тема = (д.get("headers") or {}).get("Subject", "")[:56]
    print(f"  #{р['id']} {р['event_ts'][:16]} письмо={р['message_id']} "
          f"от={отпр}")
    print(f"        {тема}")
