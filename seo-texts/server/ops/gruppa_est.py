# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
n = 0
имена = {}
for r in c.execute("SELECT id, extra_json FROM recipients "
                   " WHERE COALESCE(extra_json,'') LIKE '%gruppy%'"):
    try:
        гр = (json.loads(r[1] or "{}") or {}).get("gruppy") or []
    except Exception:
        continue
    for g in гр:
        имена[g] = имена.get(g, 0) + 1
    if "Спасённые 182" in гр:
        n += 1
print("получателей с меткой «Спасённые 182»: %d" % n)
print("все группы в базе (топ):")
for g, k in sorted(имена.items(), key=lambda kv: -kv[1])[:12]:
    print("   %-34s %5d" % (g[:34], k))
print("")
print("с target_division в extra:", c.execute(
    "SELECT COUNT(*) FROM recipients WHERE COALESCE(extra_json,'') "
    " LIKE '%target_division%'").fetchone()[0])
c.close()
