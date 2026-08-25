# -*- coding: utf-8 -*-
"""Какие группы получателей есть и что подгрузили сегодня."""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
кол = [р[1] for р in c.execute("PRAGMA table_info(recipients)")]
print("recipients: %s\n" % ", ".join(кол))

print("=== ПОЛУЧАТЕЛИ ПО ДНЯМ ЗАВЕДЕНИЯ ===")
for р in c.execute("SELECT substr(created_at,1,10) д, COUNT(*) n FROM recipients "
                   " GROUP BY д ORDER BY д DESC LIMIT 8"):
    print("   %s  %6d" % (р["д"], р["n"]))

таблицы = [р[0] for р in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%group%'")]
print("\nтаблицы групп: %s" % ", ".join(таблицы))
for т in таблицы:
    кол2 = [р[1] for р in c.execute("PRAGMA table_info(%s)" % т)]
    print("   %s: %s" % (т, ", ".join(кол2)))

if "recipient_groups" in таблицы:
    print("\n=== РАЗМЕР ГРУПП ===")
    for р in c.execute(
            "SELECT g.name, COUNT(*) n FROM recipient_groups g "
            "  LEFT JOIN recipient_group_members m ON m.group_id=g.id "
            " GROUP BY g.name ORDER BY n DESC LIMIT 12"):
        print("   %-34s %6d" % (р["name"], р["n"]))

print("\n=== СВЕЖИЕ ПОЛУЧАТЕЛИ (сегодня) ===")
сег = c.execute("SELECT COUNT(*) FROM recipients "
                " WHERE substr(created_at,1,10)=date('now')").fetchone()[0]
print("   заведено сегодня: %d" % сег)
for р in c.execute("SELECT id, email, company_name, inn FROM recipients "
                   " WHERE substr(created_at,1,10)=date('now') LIMIT 5"):
    print("      #%-7s %-30s %s" % (р["id"], str(р["email"])[:30],
                                    str(р["company_name"] or "")[:34]))
