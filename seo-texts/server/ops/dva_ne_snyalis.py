# -*- coding: utf-8 -*-
import io, json, sqlite3
снято = set()
for с in io.open(r"C:\sender\_ops\vtorye-snyatye.jsonl", encoding="utf-8"):
    снято.add(int(json.loads(с)["review"]))
все = {}
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    все[int(d["review"])] = d["email"]
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(все))
for r in c.execute("SELECT cr.id, cr.status, cr.email, cr.reason, cr.message_id, "
                   "       m.status mst, m.sent_at "
                   "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
                   " WHERE cr.id IN (%s) AND cr.status <> 'pending'" % зн, list(все)):
    метка = "снял я" if r["id"] in снято else "НЕ Я"
    print("   rev %-6s %-10s [%s] %-30s письмо: %-10s %s | %s"
          % (r["id"], r["status"], метка, str(r["email"])[:30], r["mst"],
             str(r["sent_at"] or "-")[:16], str(r["reason"] or "")[:44]))
print("")
итог = {}
for r in c.execute("SELECT status, COUNT(*) FROM confirm_reviews "
                   " WHERE id IN (%s) GROUP BY 1" % зн, list(все)):
    итог[r[0]] = r[1]
print("статусы всей партии: %s" % итог)
c.close()
