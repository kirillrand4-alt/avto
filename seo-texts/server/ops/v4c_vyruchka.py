# -*- coding: utf-8 -*-
"""Ярус C: ждущие генерации (проба «есть»/«принимает всё», без письма, без попытки,
гейт не отсёк) — разбивка по выручке. Только чтение."""
import io
import json
import sqlite3
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
    проб[(к, в)] += 1
итого = 0
for _, n in КОР:
    итого += сч[n]
    print("%-18s %5d  (есть %d, принимает всё %d)  нарастающим %d" % (n, сч[n], проб[(n, "есть")], проб[(n, "принимает всё")], итого))
print("всего:", итого)
