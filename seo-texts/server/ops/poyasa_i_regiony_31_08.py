# -*- coding: utf-8 -*-
"""Только чтение: у кого в очереди нет пояса и известен ли регион."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ОЧЕРЕДЬ: пояс задан или нет ===")
for р in s.execute(
        "SELECT CASE WHEN COALESCE(r.tz,'')='' THEN 'ПОЯС НЕ ЗАДАН' ELSE r.tz END tz,"
        " COUNT(*) n FROM messages m JOIN recipients r ON r.id=m.recipient_id"
        " WHERE m.status='scheduled' GROUP BY tz ORDER BY n DESC"):
    print("  %-26s %4d" % (р["tz"], р["n"]))

print("\n=== У КОГО НЕТ ПОЯСА: известен ли регион ===")
c = Counter()
for р in s.execute(
        "SELECT COALESCE(NULLIF(r.region,''),'(регион пуст)') reg, COUNT(*) n"
        " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
        " WHERE m.status='scheduled' AND COALESCE(r.tz,'')=''"
        " GROUP BY reg ORDER BY n DESC LIMIT 22"):
    c[р["reg"]] = р["n"]
    print("  %-40s %4d" % (str(р["reg"])[:40], р["n"]))

пуст = s.execute(
    "SELECT COUNT(*) n FROM messages m JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.status='scheduled' AND COALESCE(r.tz,'')='' AND COALESCE(r.region,'')=''"
).fetchone()["n"]
всего_без = s.execute(
    "SELECT COUNT(*) n FROM messages m JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.status='scheduled' AND COALESCE(r.tz,'')=''").fetchone()["n"]

print("\n=== ПО ВСЕЙ БАЗЕ, ДЛЯ СРАВНЕНИЯ ===")
for р in s.execute("SELECT CASE WHEN COALESCE(tz,'')='' THEN 'без пояса'"
                   " ELSE 'пояс есть' END k, COUNT(*) n FROM recipients GROUP BY k"):
    print("  %-14s %6d" % (р["k"], р["n"]))

print("\n=== ИТОГ ===")
print("  в очереди без пояса: %d, из них и без региона: %d" % (всего_без, пуст))
print("  значит по региону можно восстановить пояс у %d писем" % (всего_без - пуст))
print("  все они сейчас уходят по Europe/Moscow — окно 09:00-14:00 МСК")
