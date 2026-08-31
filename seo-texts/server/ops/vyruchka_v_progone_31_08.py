# -*- coding: utf-8 -*-
"""Только чтение: какая выручка у компаний, которым прогон УЖЕ написал."""
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
for р in e.execute("SELECT inn, revenue_rub, revenue_year FROM companies"
                   " WHERE revenue_rub IS NOT NULL"):
    try:
        выр[str(р["inn"])] = (float(р["revenue_rub"]), р["revenue_year"])
    except Exception:
        pass

print("=== СПРАВКА ПО ООО «КАЧЕСТВЕННЫЕ ЛЮДИ» (ИНН 2521016525) ===")
for таб, зпр in (("companies", "SELECT inn,name,revenue_rub,revenue_year,okved"
                  " FROM companies WHERE inn='2521016525'"),
                 ("base_ref", "SELECT * FROM base_ref WHERE inn='2521016525'")):
    try:
        for р in e.execute(зпр):
            print("  %-10s %s" % (таб, {k: str(р[k])[:60] for k in р.keys()}))
    except Exception as ex:
        print("  %-10s %s" % (таб, str(ex)[:60]))

# письма ЭТОГО прогона: берём номера review_id из свежего лога
логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)
стр = io.open(логи[0], encoding="utf-8", errors="replace").read().splitlines()
ids = [int(m.group(1)) for x in стр for m in [re.search(r"#(\d+)\s*$", x.strip())] if m]
print("\n=== ПИСЬМА ЭТОГО ПРОГОНА: %d штук (по номерам #) ===" % len(ids))
инны = []
if ids:
    q = ",".join("?" * len(ids))
    for р in s.execute("SELECT id, inn, email FROM confirm_reviews WHERE id IN (%s)" % q, ids):
        инны.append(str(р["inn"]))

к = Counter()
низкие = []
for i in инны:
    v = выр.get(i)
    if v is None:
        к["выручка неизвестна"] += 1
        continue
    r = v[0]
    if r >= 30e6:
        к["30 млн и выше"] += 1
    elif r >= 10e6:
        к["10-30 млн"] += 1
    elif r >= 1e6:
        к["1-10 млн"] += 1
    else:
        к["меньше 1 млн"] += 1
    if r < 30e6:
        низкие.append((i, r))

print("\n=== ВЫРУЧКА У АДРЕСАТОВ ЭТОГО ПРОГОНА ===")
for k, v in к.most_common():
    print("  %-22s %4d" % (k, v))

print("\n=== ПРИМЕРЫ НИЗКОЙ ВЫРУЧКИ (до 10) ===")
for i, r in sorted(низкие, key=lambda x: x[1])[:10]:
    имя = ""
    for р in s.execute("SELECT company_name FROM recipients WHERE inn=? LIMIT 1", (i,)):
        имя = str(р["company_name"])[:38]
    print("  %-12s %8.1f млн  %s" % (i, r / 1e6, имя))

print("\n=== ИТОГ ===")
n = len(инны)
мало = sum(v for k, v in к.items() if k in ("меньше 1 млн", "1-10 млн", "10-30 млн"))
print("  писем в прогоне: %d" % n)
print("  из них компаниям с выручкой МЕНЬШЕ 30 млн: %d (%.0f%%)"
      % (мало, 100.0 * мало / max(1, n)))
print("  30 млн и выше: %d" % к.get("30 млн и выше", 0))
