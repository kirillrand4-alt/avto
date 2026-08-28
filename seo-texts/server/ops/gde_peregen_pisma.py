# -*- coding: utf-8 -*-
"""Куда делись 108 перегенерированных писем."""
import glob, io, os, re, sqlite3
from collections import Counter
л = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"), key=os.path.getmtime)[-1]
ids = [int(m) for m in re.findall(r"ОК\s+\w+\s+.*?#(\d+)",
                                  io.open(л, encoding="utf-8", errors="replace").read())]
print("в логе прогона отмечено «ОК» карточек: %d" % len(ids))
if not ids:
    raise SystemExit(0)
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(ids))
сч = Counter()
прим = []
for r in c.execute(
        "SELECT cr.id, cr.status, cr.email, cr.reason, cr.decided_by, cr.updated_at, "
        "       cr.created_at, m.status mst "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.id IN (%s)" % зн, ids):
    сч["карточка %s / письмо %s" % (r["status"], r["mst"])] += 1
    if r["status"] == "skipped" and len(прим) < 5:
        прим.append((r["id"], r["email"], str(r["reason"])[:70],
                     str(r["created_at"])[:16], str(r["updated_at"])[:16]))
for к, n in сч.most_common():
    print("   %-46s %4d" % (к, n))
print("")
print("=== снятые: когда заведены и когда решены ===")
for i, e, п, с_, у in прим:
    print("   rev %-6s %-26s создана %s решена %s" % (i, str(e)[:26], с_, у))
    print("      %s" % п)
c.close()
