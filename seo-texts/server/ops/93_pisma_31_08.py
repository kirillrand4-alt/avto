# -*- coding: utf-8 -*-
"""Только чтение: что за 93 письма на новом ящике и как вообще делится нагрузка."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== 93 письма на a.erokhin@food-sort.ru ===")
for р in s.execute("SELECT status, COUNT(*) n, MIN(created_at) c1, MAX(created_at) c2,"
                   " MIN(scheduled_at) s1, MAX(scheduled_at) s2"
                   " FROM messages WHERE mailbox_id='a.erokhin@food-sort.ru'"
                   " GROUP BY status ORDER BY n DESC"):
    print("  %-16s %4d | создано %s..%s | назначено %s..%s"
          % (р["status"], р["n"], str(р["c1"])[:16], str(р["c2"])[:16],
             str(р["s1"])[:16], str(р["s2"])[:16]))

print("\n=== РАСПРЕДЕЛЕНИЕ ПО ЯЩИКАМ, кампания 11 (Meyer) ===")
всего = 0
for р in s.execute("SELECT COALESCE(mailbox_id,'(не назначен)') m, status, COUNT(*) n"
                   " FROM messages WHERE campaign_id=11 GROUP BY m, status"
                   " ORDER BY n DESC"):
    print("  %-40s %-16s %5d" % (str(р["m"])[:40], р["status"], р["n"]))
    всего += р["n"]
print("  всего в кампании 11: %d" % всего)

print("\n=== ИТОГ: сколько дней уйдёт при лимите 5/день ===")
n = s.execute("SELECT COUNT(*) n FROM messages"
              " WHERE mailbox_id='a.erokhin@food-sort.ru'"
              " AND status IN ('scheduled','pending_review','sending')").fetchone()["n"]
print("  писем в очереди на этом ящике: %d" % n)
print("  при лимите 5 в день: %.0f дней" % (n / 5.0))
print("  если бы делились на 12 новых ящиков по 5: %.0f дней" % (n / 60.0))
