# -*- coding: utf-8 -*-
"""Кого из списка partiya-140 сняли предклассификатор и гейт адресата — с причинами.

    kto_otseyan_140.py [n_primerov=15]
"""
import io
import json
import sqlite3
import sys
from collections import Counter

N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
ид = json.load(io.open(r"C:\sender\_ops\partiya-140.json", encoding="utf-8"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
по_инн = {}
for rid, inn, имя, сег in c.execute(
        "SELECT id, inn, company_name, segment FROM recipients WHERE id IN (%s)"
        % ",".join("?" * len(ид)), ид):
    по_инн[str(inn)] = (имя, сег)
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
акт = {}
for н in range(0, len(по_инн), 400):
    к = list(по_инн)[н:н + 400]
    for inn, a in cx.execute("SELECT inn, activity FROM companies WHERE inn IN (%s)"
                             % ",".join("?" * len(к)), к):
        акт[str(inn)] = a or ""

пред = []
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    if "предкласс_отсев" not in с:
        continue
    z = json.loads(с)
    if str(z.get("inn")) in по_инн and str(z.get("inn")) not in [x for x, _ in пред]:
        пред.append((str(z.get("inn")), z.get("имя")))
print("ПРЕДКЛАССИФИКАТОР снял (по журналу): %d" % len(пред))
print("   по отраслям: %s" % dict(Counter(по_инн[i][1] for i, _ in пред).most_common()))
for i, имя in пред[:N]:
    print("   - %s [%s]: %s" % (str(имя)[:34], по_инн[i][1], акт.get(i, "")[:150].replace("\n", " ")))

гейт = []
for база in (r"C:\sender\sender.db", r"C:\sender\enrich.db"):
    try:
        b = sqlite3.connect(база, timeout=30)
        for inn, v, chem, poch, ts in b.execute(
                "SELECT inn, verdict, chem, pochemu, ts FROM target_verdicts WHERE inn IN (%s)"
                % ",".join("?" * len(по_инн)), list(по_инн)):
            if v != "покупатель":
                гейт.append((str(inn), v, chem, poch))
        print("(вердикты гейта из %s)" % база)
        break
    except sqlite3.OperationalError:
        continue
print("ГЕЙТ АДРЕСАТА: не покупатель и пр.: %d" % len(гейт))
print("   вердикты: %s" % dict(Counter(v for _, v, _, _ in гейт)))
print("   по отраслям: %s" % dict(Counter(по_инн[i][1] for i, *_ in гейт).most_common()))
for i, v, chem, poch in гейт[:N]:
    print("   - %s [%s] %s: %s" % (по_инн[i][0][:34], по_инн[i][1], v, str(poch)[:160]))
print("=== КТО ОТСЕЯН ===")
