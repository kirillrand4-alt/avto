# -*- coding: utf-8 -*-
"""Список генерации ФСА v4 (ярусы A/B, кампания 18). Только получатели с
extra volna v4-A/v4-B, у кого проба уже есть и не «неясно/отказ/мёртв»;
ОКВЭД 01 (сельхоз) — вон, если не --s-01 (владелец 22.10 решает; от 500 млн —
--s-01-500). Порядок: «есть», потом «принимает всё»; внутри — выручка.
Не берём компании с письмом/журналом генерации. Пишет _ops/spisok-v4.json.
    spisok_v4.py [--s-01 | --s-01-500]"""
import io
import json
import sqlite3
import sys
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
естьписьмо = {r[0] for r in c.execute("SELECT DISTINCT recipient_id FROM messages")}
сч, ряды = Counter(), []
for rid, em, okv, ex in c.execute("SELECT id, lower(email), okved, extra_json FROM recipients WHERE extra_json LIKE '%v4-%'"):
    x = json.loads(ex or "{}")
    if x.get("volna") not in ("v4-A", "v4-B"):
        continue
    в = проба.get(em, "")
    vr = float(x.get("revenue_rub") or 0)
    if rid in естьписьмо:
        сч["письмо уже есть"] += 1; continue
    if str(okv or "").startswith("01") and not ("--s-01" in sys.argv or ("--s-01-500" in sys.argv and vr >= 5e8)):
        сч["ОКВЭД 01 — вон"] += 1; continue
    if not в:
        сч["проба ещё не дошла (%s)" % x["volna"]] += 1; continue
    if в not in ("есть", "принимает всё"):
        сч["вон: " + в] += 1; continue
    сч["в список: %s, %s" % (x["volna"], в)] += 1
    ряды.append((0 if в == "есть" else 1, -vr, rid))
ряды.sort()
json.dump([r[2] for r in ряды], io.open(r"C:\sender\_ops\spisok-v4.json", "w"))
print("в списке:", len(ряды))
for k, v in sorted(сч.items()):
    print("  %-40s %d" % (k, v))
