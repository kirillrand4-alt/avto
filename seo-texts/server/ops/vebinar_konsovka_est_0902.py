# -*- coding: utf-8 -*-
"""Только чтение: стоит ли новая концовка во всех письмах кампании 12."""
import sqlite3
from collections import Counter

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
всего = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12").fetchone()[0]
нов = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                " AND body_rendered LIKE '%металлодетектор%'"
                " AND body_rendered LIKE '%найти решение%'"
                " OR (campaign_id=12 AND body_rendered LIKE '%металлодетектор%'"
                "     AND body_rendered LIKE '%подсказать решение%')").fetchone()[0]
стар = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                 " AND body_rendered LIKE '%актуальна ли%'").fetchone()[0]
print("писем в кампании 12: %d" % всего)
print("  со старым финалом «актуальна ли»: %d" % стар)

ф = Counter()
for р in c.execute("SELECT body_rendered b FROM messages WHERE campaign_id=12"):
    т = (р["b"] or "").split("С уважением")[0].strip()
    ф[т.split("\n\n")[-1][:58]] += 1
print("\n=== ЧЕТЫРЕ РЕДАКЦИИ КОНЦОВКИ, КАК ЛЕЖАТ В БАЗЕ ===")
for т, n in ф.most_common():
    print("  %3d писем | %s..." % (n, т))
print("  всего покрыто: %d" % sum(ф.values()))

print("\n=== ОДНА ЦЕЛИКОМ ===")
р = c.execute("SELECT body_rendered b FROM messages WHERE campaign_id=12"
              " ORDER BY id LIMIT 1").fetchone()
print("  " + р["b"].split("С уважением")[0].strip().split("\n\n")[-1])
