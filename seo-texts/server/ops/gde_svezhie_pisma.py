# -*- coding: utf-8 -*-
"""Где лежат письма сегодняшних прогонов и что из них уедет.

Владелец спросил прямо: раскиданы ли годные письма в отправку. Отвечаем
по базе, а не по памяти: состояние каждой карточки очереди, созданной
сегодня, плюс что вообще стоит с датой отправки на завтра.
"""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

БД = r"C:\sender\sender.db"
ПОРОГ = int(sys.argv[1]) if len(sys.argv) > 1 else 3441

c = sqlite3.connect(БД)
c.row_factory = sqlite3.Row

print("== карточки очереди сегодняшних прогонов (id >= %d) ==" % ПОРОГ)
ряды = c.execute(
    "SELECT id, status, email, subject, created_at, message_id "
    "FROM confirm_reviews WHERE id >= ? ORDER BY id", (ПОРОГ,)).fetchall()
print(f"всего карточек: {len(ряды)}")
print("по состоянию:", dict(Counter(r["status"] for r in ряды)))

# Что с их письмами: есть ли дата отправки.
ид = [r["message_id"] for r in ряды if r["message_id"]]
if ид:
    зн = ",".join("?" * len(ид))
    м = c.execute(
        f"SELECT id, status, scheduled_at, campaign_id FROM messages "
        f"WHERE id IN ({зн})", ид).fetchall()
    print("письма по состоянию:", dict(Counter(x["status"] for x in м)))
    даты = Counter(str(x["scheduled_at"] or "")[:10] for x in м)
    print("дата отправки:", dict(даты))

print()
print("== вся очередь панели ==")
for s, n in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                      "GROUP BY status ORDER BY n DESC"):
    print(f"  {s:<16} {n}")

завтра = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
print()
print(f"== письма с датой отправки на завтра ({завтра}) ==")
for s, n in c.execute(
        "SELECT status, COUNT(*) n FROM messages "
        "WHERE substr(scheduled_at,1,10)=? GROUP BY status", (завтра,)):
    print(f"  {s:<16} {n}")
