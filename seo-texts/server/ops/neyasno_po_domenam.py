# -*- coding: utf-8 -*-
"""«Неясно» — свойство адреса или всего домена?"""
import io
import json
import sqlite3
from collections import Counter, defaultdict

домены = set()
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    pass
s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
партия = {}
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    партия[int(d["review"])] = d["email"].lower()
зн = ",".join("?" * len(партия))
for r in s.execute(
        "SELECT email FROM confirm_reviews WHERE id IN (%s) AND status='skipped' "
        "   AND COALESCE(reason,'') LIKE '%%не добилась ответа%%'" % зн, list(партия)):
    домены.add((r[0] or "").split("@")[-1].lower())
s.close()
print("доменов, где адрес снят по «неясно»: %d" % len(домены))

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
по_дом = defaultdict(Counter)
for r in e.execute("SELECT email, probe_verdict FROM emails "
                   " WHERE COALESCE(probe_verdict,'') <> ''"):
    д = (r["email"] or "").split("@")[-1].lower()
    if д in домены:
        по_дом[д][r["probe_verdict"]] += 1
e.close()

сплошь = сmesh = 0
for д, c in по_дом.items():
    if set(c) == {"неясно"}:
        сплошь += 1
    else:
        сmesh += 1
print("   у которых ВСЕ проверенные адреса «неясно»: %d" % сплошь)
print("   где есть и другие вердикты:                %d" % сmesh)
print("   без проверенных адресов вовсе:             %d" % (len(домены) - len(по_дом)))
print("")
print("=== разрез по доменам ===")
for д in sorted(по_дом, key=lambda x: -sum(по_дом[x].values()))[:12]:
    print("   %-30s %s" % (д[:30], dict(по_дом[д])))

# то же по всей базе: сколько доменов проба вообще не видит
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
всё = defaultdict(Counter)
for r in e.execute("SELECT email, probe_verdict FROM emails "
                   " WHERE COALESCE(probe_verdict,'') <> ''"):
    всё[(r[0] or "").split("@")[-1].lower()][r[1]] += 1
e.close()
глухие = [д for д, c in всё.items() if set(c) == {"неясно"} and sum(c.values()) >= 2]
print("")
print("по ВСЕЙ базе: доменов с проверенными адресами %d" % len(всё))
print("   из них глухих к пробе (2+ адреса, все «неясно»): %d" % len(глухие))
print("   адресов в них: %d" % sum(sum(всё[д].values()) for д in глухие))
