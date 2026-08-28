# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT detail_json FROM events WHERE id=301897").fetchone()
d = json.loads(r["detail_json"] or "{}")
print("=== ПОЛНЫЙ ТЕКСТ ОТВЕТА ===")
print(str(d.get("snippet") or "")[:2000])
print("")
print("=== разбор ===")
for к in ("kind", "privyazka", "in_reply_to_hdr"):
    if к in d:
        print("   %-16s %s" % (к, str(d[к])[:100]))
l = c.execute("SELECT * FROM leads WHERE id=243").fetchone()
print("")
print("=== лид 243 ===")
for к in ("status", "reply_kind", "phone", "need", "readiness", "sla_due_at"):
    if к in l.keys():
        print("   %-12s %s" % (к, str(l[к] or "")[:200]))
c.close()
