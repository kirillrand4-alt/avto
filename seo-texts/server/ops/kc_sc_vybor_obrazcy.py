# -*- coding: utf-8 -*-
"""Образцы выбора адреса и имени (kc-sc-vybor.jsonl) рядом с исходными контактами компании. Только чтение.
    kc_sc_vybor_obrazcy.py [N=12] [--mnogo] — --mnogo: только компании, где одно ФИО стоит на нескольких почтах"""
import csv, io, json, random, sys
from collections import Counter
N = int(next((a for a in sys.argv[1:] if a.isdigit()), "12"))
ц = lambda x: "".join(c for c in str(x or "") if c.isdigit())
исх = {}
for р in csv.DictReader(io.open(r"C:\seostat\drop\drop-storage\kc_sc_rassylka.csv", encoding="utf-8-sig", errors="replace"), delimiter=";"):
    кл = ц(р["ИНН"]) or "имя:" + (р["Название компании"] or "").strip().lower()
    исх.setdefault(кл, []).append(р)
в = {}
for с in io.open(r"C:\sender\_ops\kc-sc-vybor.jsonl", encoding="utf-8"):
    x = json.loads(с); в[x["kluch"]] = x
кл = list(в)
if "--mnogo" in sys.argv:
    кл = [k for k in кл if any(n > 1 for n in Counter((р["ФИО"] or "").strip() for р in исх.get(k, []) if (р["ФИО"] or "").strip()).values())]
random.seed(17); random.shuffle(кл)
for k in кл[:N]:
    print("==", (исх.get(k) or [{}])[0].get("Название компании", "")[:50])
    for р in исх.get(k, [])[:6]: print("   было: %s | %s | %s" % (р["Почта"], р["ФИО"][:40], р["Должность"][:30]))
    for i, у in enumerate(в[k]["order"][:3]): print("   %d) %s → «%s» %s%s" % (i + 1, у["email"], у["imya"], у["rol"], " (тех)" if у["teh"] else ""))
