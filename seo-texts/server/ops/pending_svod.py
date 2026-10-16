import json, sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сч = Counter()
for cid, ca, pj, st in c.execute("SELECT cr.campaign_id, cr.created_at, cr.panel_json, m.status FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id WHERE cr.status='pending'"):
    p = json.loads(pj or "{}")
    сч[(кам.get(cid, cid), "держит флаг" if (p.get("actions") or {}).get("confirm_hold") else "свободно", st, str(ca)[:13])] += 1
for k, v in sorted(сч.items(), key=lambda x: -x[1])[:25]: print(v, k)
