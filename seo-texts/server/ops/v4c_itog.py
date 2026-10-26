# -*- coding: utf-8 -*-
"""Ярус C (volna v4-C): сколько всего, с письмом, ждёт генерации (по пробе),
отсечено гейтом, и брак генерации по причинам (журнал gen-v4c.jsonl). Только чтение."""
import io
import json
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
с_письмом = {r[0]: r[1] for r in c.execute("SELECT recipient_id, status FROM messages")}
не_пок = {str(r[0]) for r in c.execute("SELECT inn FROM target_verdicts WHERE verdict='не покупатель'")}
жур = []
for s in io.open(r"C:\sender\_ops\gen-v4c.jsonl", encoding="utf-8"):
    try:
        жур.append(json.loads(s))
    except ValueError:
        pass
попытки = {}
for z in жур:
    if z.get("inn"):
        попытки[str(z["inn"])] = z
итог = Counter()
for rid, em, inn, ex in c.execute("SELECT id, lower(email), inn, extra_json FROM recipients WHERE extra_json LIKE '%v4-C%'"):
    x = json.loads(ex or "{}")
    if x.get("volna") != "v4-C":
        continue
    итог["всего"] += 1
    if rid in с_письмом:
        итог["письмо есть (%s)" % с_письмом[rid]] += 1
        continue
    if str(inn) in не_пок:
        итог["гейт: не покупатель"] += 1
        continue
    z = попытки.get(str(inn))
    if z:
        бр = json.dumps(z.get("брак") or [], ensure_ascii=False)
        итог["попытка без письма: %s" % ("403 шлюза" if "HTTP 403" in бр else "брак")] += 1
        continue
    в = проба.get(em, "")
    итог["ждёт генерации: " + (в or "проба не дошла")] += 1
for k, n in sorted(итог.items()):
    print("%-45s %d" % (k, n))
бр = Counter()
for z in попытки.values():
    if z.get("ок"):
        continue
    for b in (z.get("брак") or [])[:1]:
        бр[str(b)[:70]] += 1
print("\nбрак (первая причина, попытки без письма):")
for k, n in бр.most_common(15):
    print("  %4d  %s" % (n, k))
