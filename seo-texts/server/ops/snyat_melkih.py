# -*- coding: utf-8 -*-
"""Снять из очереди вторые адреса компаний с ИЗВЕСТНОЙ выручкой ниже порога
(владелец 27.08: «3 ниже 30млн тоже сними, они злые»).

Компании с НЕизвестной выручкой не трогаем: владелец просил снять мелких, а
не тех, про кого нечего сказать. Без --katit только считает.
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ПОРОГ = float(next((a.split("=")[1] for a in sys.argv if a.startswith("vyruchka=")),
                   "30")) * 1e6
СЛЕД = r"C:\sender\_ops\vtorye-snyatye.jsonl"

карточки = []
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    карточки.append((str(d["inn"]), d["email"].lower(), int(d["review"])))
инны = sorted({и for и, _, _ in карточки})
print("карточек в партии: %d, порог %.0f млн, режим: %s"
      % (len(карточки), ПОРОГ / 1e6, "БОЕВОЙ" if КАТИТЬ else "вхолостую"))

# только те, что ещё в очереди
s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
зн = ",".join("?" * len(карточки))
живые = {int(r[0]) for r in s.execute(
    "SELECT id FROM confirm_reviews WHERE id IN (%s) AND status='pending'" % зн,
    [rev for _, _, rev in карточки])}
s.close()
print("ещё в очереди: %d" % len(живые))

выр, имена = {}, {}
ob = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db", uri=True, timeout=60)
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]; зн2 = ",".join("?" * len(к))
    for r in ob.execute("SELECT inn, revenue_rub, name_short FROM obzvon "
                        " WHERE inn IN (%s)" % зн2, к):
        try:
            в = float(r[1])
        except Exception:                                       # noqa: BLE001
            continue
        if в > 0:
            выр.setdefault(str(r[0]), в); имена.setdefault(str(r[0]), r[2] or "")
ob.close()
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
нет = [и for и in инны if и not in выр]
for i in range(0, len(нет), 400):
    к = нет[i:i + 400]; зн2 = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, revenue_rub, name FROM companies "
                       " WHERE inn IN (%s)" % зн2, к):
        try:
            в = float(r[1])
        except Exception:                                       # noqa: BLE001
            continue
        if в > 0:
            выр.setdefault(str(r[0]), в); имена.setdefault(str(r[0]), r[2] or "")
e.close()

снимать, сч = [], Counter()
for инн, адрес, rev in карточки:
    if rev not in живые:
        сч["уже не в очереди"] += 1
        continue
    в = выр.get(инн)
    if в is None:
        сч["выручка неизвестна - не трогаем"] += 1
    elif в < ПОРОГ:
        снимать.append((rev, инн, адрес, в))
        сч["ниже порога - снять"] += 1
    else:
        сч["остаётся"] += 1
print("")
for к, n in сч.most_common():
    print("   %-34s %5d" % (к, n))
print("")
for rev, и, а, в in снимать:
    print("   rev %-6s %-13s %-30s %14s  %s"
          % (rev, и, а[:30], "{:,.0f}".format(в).replace(",", " "),
             имена.get(и, "")[:34]))
if not КАТИТЬ or not снимать:
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
итог = Counter()
поток = io.open(СЛЕД, "a", encoding="utf-8")
for rev, инн, адрес, в in снимать:
    try:
        ок = cs.skip(rev, reason="второй адрес: выручка %.0f млн ниже порога %.0f млн"
                     % (в / 1e6, ПОРОГ / 1e6), operator="отсев мелких 27.08")
        итог["снято" if ок else "не в pending"] += 1
        if ок:
            поток.write(json.dumps(
                {"review": rev, "inn": инн, "email": адрес,
                 "prichina": "выручка ниже порога", "vyruchka": в,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
            поток.flush(); os.fsync(поток.fileno())
    except Exception as ex:                                        # noqa: BLE001
        итог["ошибка: " + str(ex)[:44]] += 1
поток.close()
print("")
print("=== итог ===")
for к, n in итог.most_common():
    print("   %-34s %5d" % (к, n))
