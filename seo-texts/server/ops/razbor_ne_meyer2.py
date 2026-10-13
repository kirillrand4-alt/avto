# -*- coding: utf-8 -*-
"""Разбор выгрузки «Meyer — не покупатель» по претензиям: чужой сайт, критика
письма вместо компании, противоречие, перенос старого «не мейер». Только чтение."""
import re
import sqlite3
from collections import Counter
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
if "--kratko" not in __import__("sys").argv: print("verified:", dict(e.execute("SELECT verified, count(*) FROM companies GROUP BY 1").fetchall()))
s = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
if 0: print("target_verdicts кол:", [r[1] for r in s.execute("PRAGMA table_info(target_verdicts)")])

ПИСЬМО = re.compile(r"письм|обеща|небезопасн|формулир|в тексте|утвержд|силикон|не находит|нельзя писать|приписан", re.I)
ПРОТИВ = re.compile(r"(?<!не )(?<!не прямой )прямой кандидат|(?<![а-я])кандидат на|— покупател|- покупател|покупатель рентгена|подходит Meyer", re.I)
св = Counter()
прим = {}
for inn, name, napr, rus, ист, поч, ver, site, cand in e.execute(
        "SELECT inn, name, verdikt_napr, verdikt_rusprom, verdikt_istochnik, verdikt_pochemu, verified, site, cand_site "
        "FROM companies WHERE verdikt_napr IN ('кц','никуда','не мейер') OR (verdikt_rusprom='не покупатель' "
        "AND coalesce(verdikt_napr,'') NOT IN ('мейер','оба','не кц'))"):
    поч = поч or ""
    к = []
    if ПИСЬМО.search(поч):
        к.append("критика письма")
    if ПРОТИВ.search(поч):
        к.append("противоречие")
    if napr == "не мейер" and ист in ("гейт", "линза") and rus == "покупатель":
        к.append("старое «не мейер» под чужим источником")
    if napr == "не мейер" and ист == "предкласс":
        к.append("отсев старого предкласса генератора")
    if ver and ver not in ("sam_sayt",):
        к.append("сайт: verified=%s" % ver)
    if not к:
        к.append("без претензий: %s/%s" % (ист, napr or rus))
    for x in к:
        св[x] += 1
        прим.setdefault(x, []).append("%s | %s" % ((name or "")[:30], поч[:110]))
import sys
for к, n in св.most_common():
    print("%-55s %d" % (к, n))
    if "--kratko" in sys.argv:
        continue
    for п in прим[к][:3]:
        print("      " + п)
print("=== РАЗБОР 2 ===")
