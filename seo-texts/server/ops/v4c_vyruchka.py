# -*- coding: utf-8 -*-
"""Ярус C: ждущие генерации (проба «есть»/«принимает всё», без письма, без попытки,
гейт не отсёк) — разбивка по выручке. Только чтение."""
import io
import json
import sqlite3
import sys
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
с_письмом = {r[0] for r in c.execute("SELECT DISTINCT recipient_id FROM messages")}
не_пок = {str(r[0]) for r in c.execute("SELECT inn FROM target_verdicts WHERE verdict='не покупатель'")}
были = set()
for s in io.open(r"C:\sender\_ops\gen-v4c.jsonl", encoding="utf-8"):
    try:
        z = json.loads(s)
    except ValueError:
        continue
    if z.get("inn"):
        были.add(str(z["inn"]))
КОР = [(1e9, "от 1 млрд"), (500e6, "500 млн – 1 млрд"), (200e6, "200–500 млн"), (100e6, "100–200 млн"),
       (50e6, "50–100 млн"), (30e6, "30–50 млн"), (10e6, "10–30 млн"), (1, "до 10 млн"), (0, "нет данных/0")]
сч, проб = Counter(), Counter()
нет_данных = []
for rid, em, inn, ex in c.execute("SELECT id, lower(email), inn, extra_json FROM recipients WHERE extra_json LIKE '%v4-C%'"):
    x = json.loads(ex or "{}")
    if x.get("volna") != "v4-C" or rid in с_письмом or str(inn) in были or str(inn) in не_пок:
        continue
    в = проба.get(em, "")
    if в not in ("есть", "принимает всё"):
        continue
    try:
        выр = float(x.get("revenue_rub") or 0)
    except (TypeError, ValueError):
        выр = 0.0
    к = next(n for порог, n in КОР if выр >= порог)
    сч[к] += 1
    if к == "нет данных/0":
        нет_данных.append((inn, em, x))
    проб[(к, в)] += 1
итого = 0
for _, n in КОР:
    итого += сч[n]
    print("%-18s %5d  (есть %d, принимает всё %d)  нарастающим %d" % (n, сч[n], проб[(n, "есть")], проб[(n, "принимает всё")], итого))
print("всего:", итого)
if "--primery" in sys.argv:
    import random
    e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
    o = sqlite3.connect(r"file:C:\sender\obzvon-index.db?mode=ro", uri=True, timeout=60)
    random.seed()
    for inn, em, x in random.sample(нет_данных, min(10, len(нет_данных))):
        имя = (c.execute("SELECT company_name, region FROM recipients WHERE inn=? LIMIT 1", (inn,)).fetchone() or ["", ""])
        ко = e.execute("SELECT site, okved, substr(activity,1,160) FROM companies WHERE inn=?", (str(inn),)).fetchone() or ("", "", "")
        об = o.execute("SELECT okved_main, ssch, revenue, status FROM obzvon WHERE inn=?", (str(inn),)).fetchone() or ("", "", "", "")
        print("\n%s | ИНН %s | %s | %s" % (имя[0], inn, имя[1] or "", em))
        print("   сайт %s | ОКВЭД %s | ССЧ %s | статус %s" % (ко[0] or "-", ко[1] or об[0] or "-", об[1] or "-", об[3] or "-"))
        print("   " + (ко[2] or x.get("activity") or "")[:160])
