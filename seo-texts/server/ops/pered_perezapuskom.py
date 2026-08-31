# -*- coding: utf-8 -*-
"""Что висит перед перезапуском панели."""
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
print("=== ПИСЬМА В НЕЗАВЕРШЁННЫХ СОСТОЯНИЯХ ===")
for r in c.execute("SELECT status, COUNT(*) n FROM messages"
                   " WHERE status IN ('sending','claimed','scheduled')"
                   " GROUP BY status"):
    print("   %-12s %5d" % (r[0], r[1]))
print("\n   в sending поимённо:")
n = 0
for r in c.execute("SELECT id, campaign_id, substr(claimed_at,1,19) взято,"
                   "       mailbox_id FROM messages WHERE status='sending'"
                   " ORDER BY id"):
    n += 1
    print("      письмо %s, кампания %s, взято %s, ящик %s" % tuple(r))
if not n:
    print("      нет — перезапуск безопасен")
c.close()
