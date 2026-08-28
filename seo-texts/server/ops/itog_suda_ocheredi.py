# -*- coding: utf-8 -*-
import io, json, sqlite3
from collections import Counter
в = {}
for с in io.open(r"C:\sender\_ops\sud-ocheredi.jsonl", encoding="utf-8"):
    try:
        d = json.loads(с)
        в[int(d["id"])] = d
    except Exception:
        pass
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
ids = [int(r[0]) for r in c.execute(
    "SELECT id FROM confirm_reviews WHERE status='pending' "
    "  AND COALESCE(kind,'outbound')<>'reply'")]
c.close()
свои = {i: в[i] for i in ids if i in в}
print("в очереди %d, отсужено %d" % (len(ids), len(свои)))
print("")
for к, n in Counter(str(d.get("verdikt") or "").replace("o", "о").replace("p", "р")
                    for d in свои.values()).most_common():
    print("   %-16s %4d  (%.0f%%)" % (к, n, 100.0 * n / max(1, len(свои))))
