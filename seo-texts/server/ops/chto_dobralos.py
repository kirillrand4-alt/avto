# -*- coding: utf-8 -*-
import json, sqlite3
from collections import Counter
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== события, созданные после запуска добора (12:53) ===")
сч = Counter()
for r in c.execute("SELECT id, event_type, event_ts, recipient_id, created_at, "
                   "       detail_json FROM events "
                   " WHERE created_at > '2026-08-28T12:53' ORDER BY id"):
    сч[r["event_type"]] += 1
    if r["event_type"] in ("reply", "reply_auto", "other", "bounce"):
        d = {}
        try:
            d = json.loads(r["detail_json"] or "{}")
        except Exception:
            pass
        h = d.get("headers") or {}
        print("   #%-7s %-11s %s rid=%-7s от %s"
              % (r["id"], r["event_type"], str(r["event_ts"])[:16], r["recipient_id"],
                 str(h.get("From") or "")[:44]))
print("")
print("итого по типам: %s" % dict(сч))
c.close()
