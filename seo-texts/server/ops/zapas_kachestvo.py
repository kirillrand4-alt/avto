# -*- coding: utf-8 -*-
"""Качество выборки 1125: мусорные локальные части и случай «оба адреса общие»."""
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.argv = sys.argv
exec(open(r"C:\sender\server\ops\zapas_kopiy_3dnya.py", encoding="utf-8")
     .read().split("print(\"\")\nprint(\"=== отсев адресов ===\")")[0])

выбор = {инн: sorted(v)[0] for инн, v in годные.items()}
МУСОР = ("gosuslugi", "noreply", "no-reply", "vacanc", "vakans", "job", "hr@",
         "rabota", "kadr", "buh", "press", "smi", "sud", "arbitr", "abuse",
         "postmaster", "webmaster", "spam", "reklama", "adv", "market",
         "podpisk", "rassylk", "news", "edo", "diadoc", "sbis", "kontur",
         "otchet", "nalog", "fss", "pfr", "sekret")
ОБЩИЕ = ("info", "mail", "office", "post", "company", "zakaz", "order",
         "priem", "reception", "ooo", "firma", "kontakt", "contact")

плохие = defaultdict(list)
for инн, v in выбор.items():
    л = v[3].split("@", 1)[0]
    for м in МУСОР:
        if м.strip("@") in л:
            плохие[м].append(v[3])
            break
print("")
print("=== подозрительные локальные части среди выбранных ===")
всего_пл = 0
for м, сп in sorted(плохие.items(), key=lambda kv: -len(kv[1])):
    всего_пл += len(сп)
    print("   %-14s %4d   %s" % (м, len(сп), ", ".join(сп[:3])[:96]))
print("   ИТОГО подозрительных: %d из %d" % (всего_пл, len(выбор)))

оба = 0
разные = 0
for инн, v in выбор.items():
    новый = v[3].split("@", 1)[0]
    старые = {a.split("@", 1)[0] for a in молч[инн]}
    н_общ = any(g in новый for g in ОБЩИЕ)
    с_общ = any(any(g in с for g in ОБЩИЕ) for с in старые)
    if н_общ and с_общ:
        оба += 1
    else:
        разные += 1
print("")
print("=== перекрытие со старым адресом ===")
print("   оба адреса общие (info@ -> office@, читает тот же человек): %d" % оба)
print("   новый адрес отличается по назначению:                      %d" % разные)

print("")
print("=== топ локальных частей выбранных ===")
for л, n in Counter(v[3].split("@", 1)[0] for v in выбор.values()).most_common(20):
    print("   %-22s %5d" % (л, n))
