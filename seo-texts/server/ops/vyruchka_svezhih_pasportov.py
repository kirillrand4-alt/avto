# -*- coding: utf-8 -*-
"""Выручка компаний, которым недавно добавили паспорт сайта — по направлениям.

Направление считаем той же цепочкой, что и генерация (target_division), а
выручку берём из базы обзвона (obzvon.revenue_rub) и обогащения
(companies.revenue_rub) — что найдётся первым.
"""
import json
import os
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
from sender.ai_letter import target_division                  # noqa: E402
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ДНЕЙ = int(next((a for a in sys.argv[1:] if a.isdigit()), "3"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

o = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=30)
o.row_factory = sqlite3.Row
дни = [r["д"] for r in o.execute(
    "SELECT DISTINCT substr(ts,1,10) д FROM site_facts ORDER BY д DESC LIMIT ?",
    (ДНЕЙ,))]
print("смотрим паспорта за: %s" % ", ".join(дни))
места = ",".join("?" * len(дни))
инны = [str(r["inn"]) for r in o.execute(
    "SELECT DISTINCT inn FROM site_facts WHERE substr(ts,1,10) IN (%s) "
    "  AND COALESCE(facts_json,'') <> ''" % места, дни)]
print("компаний со свежим паспортом: %d" % len(инны))

# выручка: сначала обзвон, потом обогащение
выручка = {}
ob = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db",
                     uri=True, timeout=30)
for i in range(0, len(инны), 400):
    кусок = инны[i:i + 400]
    зн = ",".join("?" * len(кусок))
    for r in ob.execute("SELECT inn, revenue_rub FROM obzvon "
                        " WHERE inn IN (%s) AND revenue_rub IS NOT NULL" % зн,
                        кусок):
        try:
            в = float(r[1])
        except Exception:                                     # noqa: BLE001
            continue
        if в > 0:
            выручка.setdefault(str(r[0]), в)
ob.close()
нет = [и for и in инны if и not in выручка]
for i in range(0, len(нет), 400):
    кусок = нет[i:i + 400]
    зн = ",".join("?" * len(кусок))
    for r in o.execute("SELECT inn, revenue_rub FROM companies "
                       " WHERE inn IN (%s) AND revenue_rub IS NOT NULL" % зн,
                       кусок):
        try:
            в = float(r[1])
        except Exception:                                     # noqa: BLE001
            continue
        if в > 0:
            выручка.setdefault(str(r[0]), в)
o.close()
print("из них выручка известна у: %d" % len(выручка))

# направление — по получателям в базе рассылки
c = sqlite3.connect(cfg.get("service.db_path", r"C:\sender\sender.db"),
                    timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
по_напр = defaultdict(list)
счёт = Counter()
for i in range(0, len(инны), 400):
    кусок = инны[i:i + 400]
    зн = ",".join("?" * len(кусок))
    for r in c.execute("SELECT id, inn FROM recipients WHERE inn IN (%s)" % зн,
                       кусок):
        rec = store.get_recipient(int(r["id"]))
        if rec is None:
            continue
        try:
            req = q._request(rec)
        except Exception:                                     # noqa: BLE001
            счёт["запрос не собрался"] += 1
            continue
        d = str(req.get("target_division") or "")
        if d not in ("kc", "meyer"):
            d, _ = target_division(req, default="kc")
        счёт[d] += 1
        в = выручка.get(str(r["inn"]))
        if в:
            по_напр[d].append(в)
c.close()

print("направления свежих паспортов: %s" % dict(счёт))
print("")
print("%-8s %8s %14s %14s %14s %14s"
      % ("напр", "с выручкой", "средняя", "медиана", "минимум", "максимум"))
for d, ряд in sorted(по_напр.items()):
    ряд.sort()
    print("%-8s %8d %14s %14s %14s %14s"
          % (d, len(ряд),
             "{:,.0f}".format(statistics.mean(ряд)).replace(",", " "),
             "{:,.0f}".format(statistics.median(ряд)).replace(",", " "),
             "{:,.0f}".format(ряд[0]).replace(",", " "),
             "{:,.0f}".format(ряд[-1]).replace(",", " ")))

for d, ряд in sorted(по_напр.items()):
    print("")
    print("=== %s: разбивка по размеру ===" % d)
    ступени = [(0, 50e6, "до 50 млн"), (50e6, 200e6, "50-200 млн"),
               (200e6, 1e9, "200 млн - 1 млрд"), (1e9, 10e9, "1-10 млрд"),
               (10e9, 1e15, "больше 10 млрд")]
    for низ, верх, имя in ступени:
        n = sum(1 for в in ряд if низ <= в < верх)
        if n:
            print("   %-20s %5d (%4.1f%%)" % (имя, n, 100.0 * n / len(ряд)))
