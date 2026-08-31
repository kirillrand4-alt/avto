# -*- coding: utf-8 -*-
"""Только чтение: держал ли фильтр группы. Утечка = известная выручка 0<v<30млн."""
import glob
import io
import os
import re
import sqlite3
from collections import Counter

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
выр = {}
for р in e.execute("SELECT inn, revenue_rub FROM companies"):
    выр[str(р["inn"])] = None if р["revenue_rub"] is None else float(р["revenue_rub"])

логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)
стр = io.open(логи[0], encoding="utf-8", errors="replace").read().splitlines()
ids = sorted({int(m.group(1)) for x in стр
              for m in [re.search(r"#(\d+)\s*$", x.strip())] if m})
инны = []
if ids:
    q = ",".join("?" * len(ids))
    for р in s.execute("SELECT inn FROM confirm_reviews WHERE id IN (%s)" % q, ids):
        инны.append(str(р["inn"]))

к = Counter()
утечки = []
for i in инны:
    v = выр.get(i, None)
    if v is None:
        к["нет записи (NULL)"] += 1
    elif v == 0:
        к["ровно 0 = нет данных"] += 1
    elif v >= 30e6:
        к["30 млн и выше"] += 1
    else:
        к["УТЕЧКА: известная 0<v<30млн"] += 1
        утечки.append((i, v))

print("=== ПИСЬМА ПРОГОНА: %d ===" % len(инны))
for k, v in к.most_common():
    print("  %-32s %4d (%3.0f%%)" % (k, v, 100.0 * v / max(1, len(инны))))
if утечки:
    print("\n=== УТЕЧКИ ===")
    for i, v in sorted(утечки, key=lambda x: x[1]):
        print("  %-12s %8.1f млн" % (i, v / 1e6))

print("\n=== ИТОГ ===")
print("  фильтр держал: %s" % ("НЕТ, утечек %d" % len(утечки) if утечки else "ДА, утечек нет"))
print("  прошлый прогон без фильтра: 74%% писем компаниям ниже 30 млн")
print("  этот прогон: известная выручка ниже 30 млн у %d писем" % len(утечки))
