# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
for r in c.execute("SELECT event_type, COUNT(*) n FROM events "
                   " WHERE event_type IN ('other','otchet') GROUP BY 1"):
    print("   %-10s %d" % (r["event_type"], r["n"]))
print("\nчто осталось в 'other' (последние 14):")
for r in c.execute("SELECT id, event_ts, recipient_id, detail_json FROM events "
                   " WHERE event_type='other' ORDER BY id DESC LIMIT 14"):
    d = {}
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        pass
    h = d.get("headers") or {}
    т = " ".join(str(d.get("snippet") or "").split())
    печ = sum(1 for x in т[:200] if x.isprintable()) / max(1, len(т[:200]))
    print("   ev=%-7s rid=%-6s %-40s %s%s"
          % (r["id"], r["recipient_id"], str(h.get("From") or "")[:40], т[:60],
             "   ← НЕЧИТАЕМОЕ" if т and печ < 0.85 else ""))
c.close()
