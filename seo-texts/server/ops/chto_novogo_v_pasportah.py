# -*- coding: utf-8 -*-
"""Сколько в книгах паспортов нового для нас: база, обогащение, стоп-лист."""
import io
import json
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
строки = []
for ф in ("pasporta_rf.json", "pasporta_by.json"):
    п = os.path.join(r"C:\sender\server\ops", ф)
    if os.path.exists(п):
        строки.extend(json.load(io.open(п, encoding="utf-8")))
print("компаний в книгах: %d" % len(строки))

виды = Counter()
инны, почты = set(), set()
for с in строки:
    ид = str(с["ид"])
    ц = "".join(x for x in ид if x.isdigit())
    if ид.isdigit() and len(ц) in (10, 12):
        виды["российский ИНН"] += 1
        инны.add(ц)
    elif ид.upper().startswith("BY"):
        виды["белорусский УНП"] += 1
    elif ид.upper().startswith("САЙТ") or "." in ид:
        виды["вместо номера сайт"] += 1
    else:
        виды["прочее"] += 1
    if с["почта"]:
        почты.add(с["почта"])
print("")
print("--- чем опознаётся компания ---")
for к, n in виды.most_common():
    print("   %-26s %6d" % (к, n))
print("   адресов письма уникальных: %d" % len(почты))

with store._lock:
    c = store._conn
    есть_инн = есть_почта = в_стопе_инн = в_стопе_почта = 0
    for порция in range(0, len(инны), 400):
        куски = list(инны)[порция:порция + 400]
        м = ",".join("?" * len(куски))
        есть_инн += c.execute(
            "SELECT COUNT(DISTINCT inn) FROM recipients WHERE inn IN (%s)" % м,
            куски).fetchone()[0]
        в_стопе_инн += c.execute(
            "SELECT COUNT(*) FROM suppression WHERE scope='inn' "
            "  AND value IN (%s)" % м, куски).fetchone()[0]
    сп = list(почты)
    for порция in range(0, len(сп), 400):
        куски = сп[порция:порция + 400]
        м = ",".join("?" * len(куски))
        есть_почта += c.execute(
            "SELECT COUNT(DISTINCT lower(email)) FROM recipients "
            " WHERE lower(email) IN (%s)" % м, куски).fetchone()[0]
        в_стопе_почта += c.execute(
            "SELECT COUNT(*) FROM suppression WHERE scope='email' "
            "  AND value IN (%s)" % м, куски).fetchone()[0]

обог = 0
if os.path.exists(r"C:\sender\enrich.db"):
    cx = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True)
    сп = list(инны)
    for порция in range(0, len(сп), 400):
        куски = сп[порция:порция + 400]
        м = ",".join("?" * len(куски))
        обог += cx.execute("SELECT COUNT(*) FROM companies WHERE inn IN (%s)"
                           % м, куски).fetchone()[0]
    cx.close()

print("")
print("=" * 74)
print("=== ЧТО ИЗ ЭТОГО НОВОЕ ===")
print("   российских ИНН уникальных:        %6d" % len(инны))
print("      уже есть в получателях:        %6d" % есть_инн)
print("      уже есть в обогащении:         %6d" % обог)
print("      в стоп-листе по ИНН:           %6d" % в_стопе_инн)
print("")
print("   адресов письма уникальных:        %6d" % len(почты))
print("      уже есть в получателях:        %6d" % есть_почта)
print("      в стоп-листе по адресу:        %6d" % в_стопе_почта)
