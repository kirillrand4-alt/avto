# -*- coding: utf-8 -*-
"""Добор к vyruchka_svezhih_pasportov: вся когорта свежих паспортов, не только
заведённые в рассылку; усечённое среднее; кто наверху."""
import io
import os
import sqlite3
import statistics
import sys
from collections import defaultdict

ДНЕЙ = int(next((a for a in sys.argv[1:] if a.isdigit()), "3"))
o = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=30)
o.row_factory = sqlite3.Row
дни = [r["д"] for r in o.execute(
    "SELECT DISTINCT substr(ts,1,10) д FROM site_facts ORDER BY д DESC LIMIT ?", (ДНЕЙ,))]
места = ",".join("?" * len(дни))
инны = [str(r["inn"]) for r in o.execute(
    "SELECT DISTINCT inn FROM site_facts WHERE substr(ts,1,10) IN (%s) "
    "  AND COALESCE(facts_json,'') <> ''" % места, дни)]
print("паспорта за %s: %d компаний" % (", ".join(дни), len(инны)))

выручка, имя = {}, {}
ob = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db", uri=True, timeout=30)
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in ob.execute("SELECT inn, revenue_rub, name_short FROM obzvon "
                        " WHERE inn IN (%s) AND revenue_rub IS NOT NULL" % зн, к):
        try:
            в = float(r[1])
        except Exception:                                     # noqa: BLE001
            continue
        if в > 0:
            выручка.setdefault(str(r[0]), в)
            имя.setdefault(str(r[0]), r[2] or "")
ob.close()
нет = [и for и in инны if и not in выручка]
for i in range(0, len(нет), 400):
    к = нет[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in o.execute("SELECT inn, revenue_rub, name FROM companies "
                       " WHERE inn IN (%s) AND revenue_rub IS NOT NULL" % зн, к):
        try:
            в = float(r[1])
        except Exception:                                     # noqa: BLE001
            continue
        if в > 0:
            выручка.setdefault(str(r[0]), в)
            имя.setdefault(str(r[0]), r[2] or "")
o.close()

# кто уже заведён в рассылку
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
в_рассылке = set()
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in c.execute("SELECT DISTINCT inn FROM recipients WHERE inn IN (%s)" % зн, к):
        в_рассылке.add(str(r[0]))
c.close()

def свод(имячко, ряд):
    if not ряд:
        print("%-22s  —" % имячко)
        return
    ряд = sorted(ряд)
    n = len(ряд)
    ср = statistics.mean(ряд)
    мед = statistics.median(ряд)
    рез = ряд[int(n * 0.05):n - int(n * 0.05)] or ряд
    печ = lambda в: "{:,.0f}".format(в).replace(",", " ")       # noqa: E731
    print("%-22s %6d  ср %13s  мед %12s  ср-без-хвостов %13s"
          % (имячко, n, печ(ср), печ(мед), печ(statistics.mean(рез))))

print("выручка известна у: %d (%.0f%%)"
      % (len(выручка), 100.0 * len(выручка) / max(1, len(инны))))
print("")
свод("вся когорта", list(выручка.values()))
свод("заведены в рассылку", [в for и, в in выручка.items() if и in в_рассылке])
свод("ещё не заведены", [в for и, в in выручка.items() if и not in в_рассылке])
print("")
print("не заведено в рассылку: %d из %d" % (len(инны) - len(в_рассылке), len(инны)))

ряд = sorted(выручка.values())
print("")
print("=== вся когорта: сколько дотягивает до порога ===")
for порог, п in [(10e6, "10 млн"), (50e6, "50 млн"), (100e6, "100 млн"),
                 (200e6, "200 млн"), (500e6, "500 млн"), (1e9, "1 млрд")]:
    n = sum(1 for в in ряд if в >= порог)
    print("   от %-8s %6d (%4.1f%%)" % (п, n, 100.0 * n / len(ряд)))

print("")
print("=== десятка по выручке ===")
for и, в in sorted(выручка.items(), key=lambda kv: -kv[1])[:10]:
    print("   %-14s %16s  %s%s"
          % (и, "{:,.0f}".format(в).replace(",", " "), имя.get(и, "")[:52],
             "" if и in в_рассылке else "   [не в рассылке]"))
