# -*- coding: utf-8 -*-
"""Только чтение: отправляли ли что-нибудь новые ящики."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
кол = [r["name"] for r in s.execute("PRAGMA table_info(send_log)")]
print("=== send_log колонки ===")
print("  " + ", ".join(кол))
поле = next((k for k in кол if "mailbox" in k.lower()), None)
print("  поле ящика: %s" % поле)

НОВЫЕ = ("food-sort.ru", "sorting-systems.ru", "rentgen-control.ru",
         "optical-sort.ru", "rentgen-inspection.ru", "inspection-systems.ru")

if поле:
    c = Counter()
    for р in s.execute("SELECT %s m, COUNT(*) n FROM send_log GROUP BY m" % поле):
        c[str(р["m"])] = р["n"]
    print("\n=== ОТПРАВКИ ПО НОВЫМ ЯЩИКАМ (send_log) ===")
    нашлось = 0
    for m, n in sorted(c.items()):
        if any(d in m for d in НОВЫЕ):
            print("  %-40s %d" % (m, n))
            нашлось += n
    print("  ИТОГО с новых ящиков: %d" % нашлось)
    print("\n  всего записей send_log: %d" % sum(c.values()))

print("\n=== messages: есть ли письма, назначенные новым ящикам ===")
try:
    n = 0
    for р in s.execute("SELECT mailbox_id, COUNT(*) k FROM messages"
                       " WHERE mailbox_id IS NOT NULL GROUP BY mailbox_id"):
        if any(d in str(р["mailbox_id"]) for d in НОВЫЕ):
            print("  %-40s %d" % (р["mailbox_id"], р["k"]))
            n += р["k"]
    print("  ИТОГО назначено новым: %d" % n)
except Exception as ex:
    print("  ", str(ex)[:90])

print("\n=== ИТОГ ===")
print("  sent_total из mailbox_state у новых:")
for р in s.execute("SELECT mailbox_id, sent_total, sent_today FROM mailbox_state"):
    if any(d in str(р["mailbox_id"]) for d in НОВЫЕ):
        print("  %-40s всего %s, сегодня %s"
              % (р["mailbox_id"], р["sent_total"], р["sent_today"]))
