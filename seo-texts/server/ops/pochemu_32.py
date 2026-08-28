# -*- coding: utf-8 -*-
import io, json, sqlite3
from collections import Counter
ids = []
for с in io.open(r"C:\sender\_ops\v-avtootpravku.jsonl", encoding="utf-8"):
    d = json.loads(с)
    if "review" in d:
        ids.append(int(d["review"]))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(ids))
пр = Counter()
прим = []
for r in c.execute(
        "SELECT cr.email, m.last_error, m.updated_at FROM messages m "
        "  JOIN confirm_reviews cr ON cr.message_id=m.id "
        " WHERE cr.id IN (%s) AND m.status='skipped'" % зн, ids):
    к = str(r["last_error"] or "—")[:60]
    пр[к] += 1
    if len(прим) < 6:
        прим.append((r["email"], к, str(r["updated_at"])[:16]))
for к, n in пр.most_common():
    print("   %-62s %4d" % (к, n))
print("")
for e, к, t in прим:
    print("   %-30s %s  (%s)" % (str(e)[:30], к[:40], t))
c.close()
