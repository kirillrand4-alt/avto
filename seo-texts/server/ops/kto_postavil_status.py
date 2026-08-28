# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== история лида 243 ===")
кол = [r[1] for r in c.execute("PRAGMA table_info(lead_events)")]
print("   колонки lead_events: %s" % ", ".join(кол))
for r in c.execute("SELECT * FROM lead_events WHERE lead_id=243 ORDER BY id"):
    print("   " + " | ".join("%s=%s" % (к, str(r[к])[:60]) for к in r.keys()
                             if r[к] not in (None, "")))
print("")
print("=== кто вообще ставит not_interested (по всем лидам) ===")
try:
    for r in c.execute("SELECT action, to_status, COUNT(*) n, "
                       "       COALESCE(actor,'—') кто FROM lead_events "
                       " WHERE to_status='not_interested' GROUP BY 1,2,4 "
                       " ORDER BY n DESC LIMIT 10"):
        print("   %-16s -> %-16s %-24s %4d" % (r["action"], r["to_status"],
                                               r["кто"], r["n"]))
except Exception as e:
    for r in c.execute("SELECT action, to_status, COUNT(*) n FROM lead_events "
                       " WHERE to_status='not_interested' GROUP BY 1,2 "
                       " ORDER BY n DESC LIMIT 10"):
        print("   %-16s -> %-16s %4d" % (r["action"], r["to_status"], r["n"]))
c.close()
