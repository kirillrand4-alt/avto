# -*- coding: utf-8 -*-
import io, json, sqlite3
from collections import Counter
в = [json.loads(с) for с in io.open(r"C:\sender\_ops\sud-vtoryh.jsonl", encoding="utf-8")]
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
карта = {}
зн = ",".join("?" * len(в))
for r in c.execute("SELECT cr.id, cr.subject, r.company_name, r.okved "
                   "  FROM confirm_reviews cr LEFT JOIN recipients r "
                   "    ON r.id=cr.recipient_id WHERE cr.id IN (%s)" % зн,
                   [x["id"] for x in в]):
    карта[int(r["id"])] = (str(r["company_name"] or "")[:40],
                           str(r["okved"] or "")[:46], str(r["subject"] or "")[:44])
c.close()
print("=== НЕ ОТПРАВЛЯТЬ ===")
for x in в:
    if x.get("verdikt") != "не отправлять":
        continue
    к = карта.get(int(x["id"]), ("?", "?", "?"))
    print("rev %-6s %s" % (x["id"], к[0]))
    print("   ОКВЭД: %s" % к[1])
    print("   тема:  %s" % к[2])
    print("   не так: %s" % str(x.get("chto_ne_tak"))[:130])
    if (x.get("vydumka") or "").strip():
        print("   выдумка: %s" % str(x["vydumka"])[:110])
    print("   направление: %s" % str(x.get("napravlenie_pochemu"))[:110])
