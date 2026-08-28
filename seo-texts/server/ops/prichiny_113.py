# -*- coding: utf-8 -*-
import sqlite3
from collections import Counter
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
пр = Counter()
кто = Counter()
for r in c.execute(
        "SELECT cr.reason, cr.decided_by FROM confirm_reviews cr "
        "  JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE r.extra_json LIKE '%peregen2%' AND cr.status='skipped' "
        "   AND substr(cr.created_at,1,10)='2026-08-28'"):
    п = str(r["reason"] or "—")
    пр[п.split("—")[0].split(":")[0][:46]] += 1
    кто[str(r["decided_by"] or "—")[:34]] += 1
print("=== причины снятия карточек, заведённых сегодня ===")
for к, n in пр.most_common():
    print("   %-48s %4d" % (к, n))
print("")
print("=== кто снял ===")
for к, n in кто.most_common():
    print("   %-36s %4d" % (к, n))
c.close()
