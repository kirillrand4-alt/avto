# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT * FROM events WHERE id=?", (293944,)).fetchone()
if r is None:
    print("события нет")
else:
    for к in r.keys():
        v = r[к]
        if к in ("detail_json", "payload_json") and v:
            try:
                d = json.loads(v)
                print("%s:" % к)
                for kk, vv in d.items():
                    print("    %-18s %s" % (kk, str(vv)[:300]))
                continue
            except Exception:
                pass
        print("%-16s %s" % (к, str(v)[:300]))
print("")
print("=== соседние входящие вне переписки за сегодня ===")
for x in c.execute(
        "SELECT id, event_type, recipient_id, mailbox_id, event_ts, dedup_key "
        "  FROM events WHERE substr(event_ts,1,10)=date('now') "
        "   AND recipient_id IS NULL ORDER BY id DESC LIMIT 10"):
    print("   #%-7s %-14s ящик %-30s %s"
          % (x["id"], x["event_type"], str(x["mailbox_id"])[:30],
             str(x["dedup_key"])[:40]))
c.close()
