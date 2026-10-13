# -*- coding: utf-8 -*-
"""Свод проверок адресов групп «Россия 9000»/«Белорусь 1000»: жива ли SMTP-проба,
у кого нет SMTP-вердикта, у кого нет лёгкой проверки (MX), запасные по лесенке."""
import io
import json
import os
import sqlite3
import subprocess
from collections import Counter
pid = io.open(r"C:\sender\_ops\smtp-proba-partiy.pid").read().strip()
жив = pid in subprocess.run(["tasklist", "/FI", "PID eq %s" % pid], capture_output=True, text=True).stdout
print("SMTP-проба: pid %s, жива: %s" % (pid, жив))
try:
    л = json.load(io.open(r"C:\sender\_ops\lyogkaya-progress.json", encoding="utf-8"))
    print("лёгкая проверка (MX), прогресс: %s" % json.dumps(л, ensure_ascii=False)[:300])
except Exception as е:  # noqa: BLE001
    print("лёгкая проверка: файла хода нет (%s)" % е)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
вер = {р[0].lower(): р[1] for р in c.execute("SELECT email, verdict FROM addr_probe")}
осн = []
for р in c.execute("SELECT id, inn, lower(email) e, created_at, extra_json FROM recipients "
                   "WHERE extra_json LIKE '%gruppy%'"):
    try:
        гр = (json.loads(р[4] or "{}") or {}).get("gruppy") or []
    except Exception:  # noqa: BLE001
        continue
    if any(г in гр for г in ("Россия 9000", "Белорусь 1000")):
        осн.append((р[0], р[1], р[2], str(р[3])[:10]))
без = [x for x in осн if x[2] not in вер]
print("основных адресов в группах: %d; без SMTP-вердикта: %d (из них заведены 13.10: %d)" % (
    len(осн), len(без), sum(1 for x in без if x[3] >= "2026-10-13")))
print("вердикты основных: %s" % dict(Counter(вер.get(x[2], "нет вердикта") for x in осн).most_common()))
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
инны = list({x[1] for x in осн if x[1]})
всего = mx_нет = mx_есть = mx_плохо = 0
по_ролям = Counter()
for н in range(0, len(инны), 400):
    к = инны[н:н + 400]
    for е, mx, pv in cx.execute("SELECT lower(email), mx_ok, probe_verdict FROM emails WHERE inn IN (%s)"
                                % ",".join("?" * len(к)), к):
        всего += 1
        if mx is None or mx == "":
            mx_нет += 1
        elif str(mx) in ("1", "True", "true", "ok"):
            mx_есть += 1
        else:
            mx_плохо += 1
        по_ролям["SMTP есть" if (pv or вер.get(е)) else "SMTP нет"] += 1
print("все адреса этих компаний в обогащении: %d; MX: ок %d, плохо %d, НЕ ПРОВЕРЕН %d" % (всего, mx_есть, mx_плохо, mx_нет))
print("SMTP-проба по всем адресам компаний: %s" % dict(по_ролям))
try:
    лёг = json.load(io.open(r"C:\sender\_ops\lyogkaya-progress.json", encoding="utf-8"))
except Exception:  # noqa: BLE001
    лёг = {}
домены_без = Counter(x[2].rsplit("@", 1)[-1] for x in без)
print("лёгкая проверка: доменов в файле %d, из них мёртвых %d" % (len(лёг), sum(1 for v in лёг.values() if isinstance(v, dict) and v.get("mertv"))))
print("у адресов без SMTP-вердикта (%d) домен прошёл лёгкую: %d адресов; не прошёл/не проверен: %d" % (
    len(без), sum(n for д, n in домены_без.items() if д in лёг), sum(n for д, n in домены_без.items() if д not in лёг)))
print("топ доменов без SMTP-вердикта: %s" % dict(домены_без.most_common(8)))
print("=== СВОД ПРОВЕРОК ===")
