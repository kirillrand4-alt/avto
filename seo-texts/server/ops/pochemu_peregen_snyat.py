# -*- coding: utf-8 -*-
import sqlite3
from collections import Counter
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
пр = Counter()
прим = []
for r in c.execute(
        "SELECT cr.id, cr.email, cr.reason, cr.decided_by, cr.status "
        "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE r.extra_json LIKE '%peregen2%' AND cr.created_at >= date('now') "
        "   AND cr.status='skipped'"):
    к = str(r["reason"] or "—")
    к = к.split(":")[0][:44] if ":" in к else к[:44]
    пр[к] += 1
    if len(прим) < 5:
        прим.append((r["id"], r["email"], str(r["reason"])[:80], r["decided_by"]))
for к, n in пр.most_common():
    print("   %-48s %4d" % (к, n))
print("")
for i, e, п, d in прим:
    print("   rev %-6s %-28s %s | %s" % (i, str(e)[:28], п, d))
print("")
print("=== что из peregen2 в работе ===")
for r in c.execute(
        "SELECT cr.status, m.status mst, COUNT(*) n "
        "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE r.extra_json LIKE '%peregen2%' AND cr.created_at >= date('now') "
        " GROUP BY 1,2"):
    print("   карточка %-10s письмо %-12s %4d" % (r["status"], r["mst"], r["n"]))
c.close()
