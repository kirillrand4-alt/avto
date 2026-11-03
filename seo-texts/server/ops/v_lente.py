# -*- coding: utf-8 -*-
"""Есть ли по адресам событие ответа и лид в ленте; когда watcher последний раз писал событие."""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
lc = [r[1] for r in c.execute("PRAGMA table_info(leads)")]
ec = [r[1] for r in c.execute("PRAGMA table_info(events)")]
print("последнее событие:", c.execute("SELECT MAX(%s) FROM events" % ("ts" if "ts" in ec else "created_at")).fetchone())
for e in sys.argv[1:]:
    rid = [r[0] for r in c.execute("SELECT id FROM recipients WHERE lower(email)=?", (e.lower(),))]
    ев = c.execute("SELECT event_type, %s FROM events WHERE recipient_id IN (%s) ORDER BY id DESC LIMIT 2" % ("ts" if "ts" in ec else "created_at", ",".join(map(str, rid)) or "0")).fetchall()
    лид = c.execute("SELECT * FROM leads WHERE recipient_id IN (%s) ORDER BY id DESC LIMIT 1" % (",".join(map(str, rid)) or "0")).fetchone()
    print(e, "| получатель", rid, "| события", ев, "| лид", (dict(zip(lc, лид)).get("status"), dict(zip(lc, лид)).get("priority")) if лид else None)
