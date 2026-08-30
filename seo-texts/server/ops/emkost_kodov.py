# -*- coding: utf-8 -*-
"""Ёмкость каждого кода из задания: сколько компаний у чеко всего.

Один запрос на код (page=1) отдаёт ЗапВсего и СтрВсего — этого хватает, чтобы
посчитать и объём рынка, и цену добора в запросах. Ходим живыми ключами из
C:\\sender\\_ops\\checko-zhivye-klyuchi.txt.

Результат — в серверный json + jsonl, не только в вывод.
"""
import csv
import io
import json
import os
import re
import sys
import time
from collections import Counter

КОРЕНЬ = r"C:\seostat\Parser2"
sys.path.insert(0, КОРЕНЬ)
КОДЫ = os.path.join(КОРЕНЬ, "data", "okved-agro.txt")
CSV_ = os.path.join(КОРЕНЬ, "data", "agro-base.csv")
ЖИВЫЕ = r"C:\sender\_ops\checko-zhivye-klyuchi.txt"
ВЫХОД = r"C:\sender\_ops\checko-emkost.json"
ЖУРНАЛ = r"C:\sender\_ops\checko-emkost.jsonl"

import requests                                              # noqa: E402
from metalparser.checko import (build_search_params,          # noqa: E402
                                SEARCH_URL, DEFAULT_UA)

ключи = [с.strip() for с in io.open(ЖИВЫЕ, encoding="utf-8") if с.strip()]
задание = [с.strip() for с in io.open(КОДЫ, encoding="utf-8") if с.strip()]
print("живых ключей: %d, кодов: %d" % (len(ключи), len(задание)))
if not ключи:
    print("нет живых ключей — выхожу")
    raise SystemExit(0)

собрано = Counter()
with io.open(CSV_, encoding="utf-8-sig", errors="ignore", newline="") as f:
    for ряд in csv.DictReader(f, delimiter=";"):
        к = str(ряд.get("Основной ОКВЭД") or "").strip()
        if к:
            собрано[к.split()[0]] += 1

было = {}
if os.path.exists(ВЫХОД):
    try:
        было = json.load(io.open(ВЫХОД, encoding="utf-8"))
    except Exception:                                         # noqa: BLE001
        было = {}

ёмкость = dict(было)
н = 0
for i, код in enumerate(задание):
    if код in ёмкость:
        continue
    ключ = ключи[i % len(ключи)]
    п = {**build_search_params(код, None, True, 1), "key": ключ}
    try:
        r = requests.get(SEARCH_URL, params=п, timeout=30,
                         headers={"User-Agent": DEFAULT_UA})
        pl = r.json()
    except Exception as e:                                    # noqa: BLE001
        print("   %-10s ошибка %s" % (код, type(e).__name__))
        time.sleep(1.0)
        continue
    d = (pl or {}).get("data") or {}
    всего = d.get("ЗапВсего")
    стр = d.get("СтрВсего")
    if всего is None:
        м = ((pl or {}).get("meta") or {}).get("message") or ""
        print("   %-10s нет данных: %s" % (код, str(м)[:70]))
        time.sleep(1.0)
        continue
    ёмкость[код] = {"vsego": int(всего), "stranic": int(стр or 0)}
    н += 1
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time()), "kod": код,
                            "vsego": int(всего), "stranic": int(стр or 0)},
                           ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    time.sleep(0.8)

with io.open(ВЫХОД, "w", encoding="utf-8") as f:
    json.dump(ёмкость, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())

строки = []
для_добора, стр_добора = 0, 0
for код in задание:
    e = ёмкость.get(код)
    if not e:
        continue
    есть = собрано.get(код, 0)
    нехват = max(0, e["vsego"] - есть)
    строки.append((нехват, код, e["vsego"], есть, e["stranic"]))
    если_брать = max(0, e["stranic"] - есть // 100)
    if нехват > 0:
        для_добора += нехват
        стр_добора += если_брать

строки.sort(reverse=True)
print("\n=== ЁМКОСТЬ КОДОВ (спрошено сейчас: %d) ===" % н)
print("   %-10s %9s %9s %9s" % ("код", "у чеко", "у нас", "не хватает"))
for нехват, код, всего, есть, стр in строки[:70]:
    print("   %-10s %9d %9d %9d" % (код, всего, есть, нехват))

print("\n=== ИТОГ ===")
print("кодов измерено: %d из %d" % (len(ёмкость), len(задание)))
print("всего компаний у чеко по этим кодам: %d"
      % sum(e["vsego"] for e in ёмкость.values()))
print("у нас собрано по ним: %d" % sum(собрано.get(к, 0) for к in ёмкость))
print("остаётся добрать: %d компаний ≈ %d запросов" % (для_добора, стр_добора))
print("живых ключей %d → суточный потолок ≈ %d запросов; хватит на %.1f дня"
      % (len(ключи), len(ключи) * 100,
         стр_добора / float(max(1, len(ключи) * 100))))
