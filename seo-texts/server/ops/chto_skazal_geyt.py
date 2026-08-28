# -*- coding: utf-8 -*-
"""Что гейт заходов сказал про компании, которых забраковал судья писем."""
import io
import json
import sqlite3
from collections import Counter

нельзя = {}
for с in io.open(r"C:\sender\_ops\sud-vtoryh.jsonl", encoding="utf-8"):
    try:
        d = json.loads(с)
    except Exception:                                            # noqa: BLE001
        continue
    if str(d.get("verdikt")) == "не отправлять":
        нельзя[int(d["id"])] = d
print("забраковано судьёй: %d" % len(нельзя))

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
кол = [r[1] for r in c.execute("PRAGMA table_info(target_verdicts)")]
print("колонки target_verdicts: %s" % ", ".join(кол))
всего = c.execute("SELECT COUNT(*) FROM target_verdicts").fetchone()[0]
раскл = dict(c.execute("SELECT verdict, COUNT(*) FROM target_verdicts "
                       "GROUP BY 1").fetchall())
print("вердиктов гейта всего: %d, раскладка: %s" % (всего, раскл))

зн = ",".join("?" * len(нельзя))
инны = {}
for r in c.execute("SELECT cr.id, cr.inn, r.okved, r.company_name "
                   "  FROM confirm_reviews cr LEFT JOIN recipients r "
                   "    ON r.id=cr.recipient_id WHERE cr.id IN (%s)" % зн,
                   list(нельзя)):
    инны[str(r["inn"])] = (int(r["id"]), str(r["okved"] or ""),
                           str(r["company_name"] or ""))
print("компаний: %d" % len(инны))

сп = sorted(инны)
зн2 = ",".join("?" * len(сп))
гейт = {}
for r in c.execute("SELECT * FROM target_verdicts WHERE inn IN (%s)" % зн2, сп):
    гейт[str(r["inn"])] = dict(r)
c.close()
print("")
print("=== что сказал гейт про них ===")
сч = Counter()
for инн in сп:
    g = гейт.get(инн)
    сч[str(g.get("verdict")) if g else "гейт их НЕ СУДИЛ"] += 1
for к, n in сч.most_common():
    print("   %-26s %4d" % (к, n))
print("")
print("=== примеры ===")
n = 0
for инн in сп:
    g = гейт.get(инн)
    rev, оквэд, имя = инны[инн]
    if n >= 8:
        break
    n += 1
    print("   %-13s %-30s ОКВЭД %-9s гейт: %s"
          % (инн, имя[:30], оквэд[:9], (g or {}).get("verdict", "не судил")))
    print("      судья: %s" % str(нельзя[rev].get("chto_ne_tak"))[:96])
    if g and g.get("reason"):
        print("      гейт:  %s" % str(g.get("reason"))[:96])
