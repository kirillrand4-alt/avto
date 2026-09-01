# -*- coding: utf-8 -*-
"""Только чтение: с какой скоростью новый ящик отправлял в первый день."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
Я = "a.erokhin@food-sort.ru"

print("=== ОТПРАВКИ %s ПО ЧАСАМ ===" % Я)
c = Counter()
for р in s.execute("SELECT sent_at FROM messages WHERE mailbox_id=? AND status='sent'"
                   " AND sent_at IS NOT NULL", (Я,)):
    c[str(р["sent_at"])[:13]] += 1
итого = 0
for k in sorted(c):
    итого += c[k]
    print("  %s  %3d  (накопительно %3d)" % (k, c[k], итого))

print("\n=== ПО ДНЯМ ===")
д = Counter()
for р in s.execute("SELECT sent_at FROM messages WHERE mailbox_id=? AND status='sent'"
                   " AND sent_at IS NOT NULL", (Я,)):
    д[str(р["sent_at"])[:10]] += 1
for k in sorted(д):
    print("  %s  %3d писем   <- кривая прогрева на день 0 даёт 3, на день 1 даёт 5"
          % (k, д[k]))

print("\n=== ДЛЯ СРАВНЕНИЯ: старый прогретый ящик ===")
for р in s.execute("SELECT mailbox_id, substr(sent_at,1,10) д, COUNT(*) n"
                   " FROM messages WHERE mailbox_id='a.miroshnichenko@optic-sort.ru'"
                   " AND status='sent' AND sent_at IS NOT NULL"
                   " GROUP BY д ORDER BY д DESC LIMIT 6"):
    print("  %s  %s  %d" % (р["mailbox_id"][:32], р["д"], р["n"]))

print("\n=== ИТОГ ===")
всего = sum(д.values())
дней = len(д)
print("  %s отправил %d писем за %d дн." % (Я, всего, дней))
print("  по кривой прогрева за столько дней разрешено: %d" % (3 + 5 * max(0, дней - 1)))
print("  превышение: в %.0f раз" % (всего / max(1, 3 + 5 * max(0, дней - 1))))
print("  при этом mailbox_state.sent_total = 0 — счётчик не считал ничего")
