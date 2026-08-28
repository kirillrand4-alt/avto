# -*- coding: utf-8 -*-
import io, json, sqlite3
from collections import Counter
партии = {}
for ф, п in ((r"C:\sender\_ops\vtorye-adresa.jsonl", 1),
             (r"C:\sender\_ops\vtorye-adresa-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "review" in d:
                партии[int(d["review"])] = п
    except FileNotFoundError:
        pass
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(партии))
ids = list(партии)
print("карточек в обеих партиях: %d" % len(ids))
по = Counter()
for r in c.execute("SELECT id, status FROM confirm_reviews WHERE id IN (%s)" % зн, ids):
    по["п%d %s" % (партии[int(r["id"])], r["status"])] += 1
for к, n in sorted(по.items()):
    print("   %-16s %5d" % (к, n))
print("")
print("=== письма партий ===")
for r in c.execute(
        "SELECT m.status, COUNT(*) FROM messages m JOIN confirm_reviews cr "
        "  ON cr.message_id=m.id WHERE cr.id IN (%s) GROUP BY 1 ORDER BY 2 DESC" % зн,
        ids):
    print("   %-12s %5d" % (r[0], r[1]))
print("")
print("=== отправлено сегодня всего (вся база) ===")
print("   ", dict(c.execute(
    "SELECT m.status, COUNT(*) FROM messages m "
    " WHERE substr(COALESCE(m.sent_at,m.scheduled_at),1,10)=date('now') "
    " GROUP BY 1").fetchall()))
c.close()
