# -*- coding: utf-8 -*-
"""Живёт ли работник проб и как приговорённые адреса попали в approved."""
import sqlite3
import time

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row

print("=== ТЕМП ПРОБ ===")
for r in c.execute("SELECT substr(ts,1,10) д, COUNT(*) n FROM addr_probe"
                   " GROUP BY д ORDER BY д DESC LIMIT 8"):
    print("   %s  %6d" % (r[0], r[1]))
r = c.execute("SELECT MAX(ts) FROM addr_probe").fetchone()[0]
print("   последняя проба: %s" % r)

print("\n=== ВЕРДИКТЫ ВСЕГО ===")
for r in c.execute("SELECT verdict, COUNT(*) n FROM addr_probe"
                   " GROUP BY verdict ORDER BY n DESC"):
    print("   %-22s %6d" % (r[0], r[1]))

print("\n=== ЧЕТЫРЕ ПРИГОВОРЁННЫХ В ОЧЕРЕДИ ===")
for адрес in ("bux-td-rp@yandex.ru", "konditer.nizh@mail.ru",
              "fmp@zolotoiparus.ru", "ooo.hleb.tih@yandex.ru"):
    p = c.execute("SELECT verdict, ts, answer FROM addr_probe WHERE email=?",
                  (адрес,)).fetchone()
    cr = c.execute("SELECT id, status, decided_at, created_at, message_id"
                   "  FROM confirm_reviews WHERE email=? "
                   " ORDER BY id DESC LIMIT 1", (адрес,)).fetchone()
    m = None
    if cr and cr["message_id"]:
        m = c.execute("SELECT status, sent_at, scheduled_at FROM messages"
                      " WHERE id=?", (cr["message_id"],)).fetchone()
    print("   %s" % адрес)
    print("      проба:  %-12s %s  %s"
          % (p["verdict"], p["ts"], str(p["answer"] or "")[:60]))
    print("      письмо: review %s, создано %s, одобрено %s"
          % (cr["id"], cr["created_at"], cr["decided_at"]))
    if m:
        print("      статус: %s, в расписании %s, отправлено %s"
              % (m["status"], m["scheduled_at"], m["sent_at"]))
    поздно = p["ts"] and cr["decided_at"] and str(p["ts"]) > str(cr["decided_at"])
    print("      вердикт пришёл ПОСЛЕ одобрения: %s" % ("да" if поздно else "НЕТ"))

print("\n=== СКОЛЬКО ЖДЁТ ПРОБЫ ===")
r = c.execute(
    "SELECT COUNT(DISTINCT cr.email) FROM confirm_reviews cr"
    " LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
    " WHERE cr.status IN ('pending','approved','edited') AND p.email IS NULL"
).fetchone()[0]
print("   адресов живой очереди без пробы: %d" % r)
c.close()
print("\n=== ИТОГ ===")
print("если последняя проба старше нескольких часов — работник стоит,")
print("и 98%% сегодняшней партии уедет непроверенными.")
