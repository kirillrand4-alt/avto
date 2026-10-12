# -*- coding: utf-8 -*-
"""Есть ли у нас «боли отраслей» и достают ли они до книг паспортов.

Владелец 12.10: «а у нас нету "болей" отраслей? сейчас несколько писем
готовлю под разные отрасли ещё».

Карта болей живёт в okved-pains.json и ключуется ОКВЭДом. В книгах
«Основной ОКВЭД» заполнен только у части строк, зато «Направление»
(16 отраслей) есть у всех — поэтому важно посчитать, сколько компаний
получат точную боль, а сколько свалятся в общий дефолт направления.
"""
import glob
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
from sender import ai_letter                                     # noqa: E402

print("файл болей: %s" % ai_letter.OKVED_PAINS_PATH)
pains = ai_letter._okved_pains()
print("разделы файла:")
for k, v in pains.items():
    print("   %-22s %s" % (k, len(v) if isinstance(v, dict) else str(v)[:60]))
град = pains.get("_meyer_gradaciya") or {}
print("карта градаций (код → станок): %d кодов" % len(град))
for k in sorted(град)[:12]:
    print("      %-8s %s" % (k, град[k]))

компании = []
for п in sorted(glob.glob(r"C:\sender\server\ops\knigi_*.json")):
    компании.extend((json.load(io.open(п, encoding="utf-8")).get("компании") or []))

есть_код = 0
точных, дефолтных = Counter(), Counter()
станки = Counter()
по_отrasli = {}
for к in компании:
    отр = str(к.get("otrasl") or "(нет)")
    код = str(к.get("okved") or "").strip()
    д = по_отrasli.setdefault(отр, Counter())
    д["всего"] += 1
    if not код:
        д["кода нет"] += 1
        дефолтных["кода нет вовсе"] += 1
        continue
    есть_код += 1
    боль, нашлось = ai_letter.боль_по_кодам([код], "meyer")
    станки[ai_letter._градация_мейера(код, pains)] += 1
    if нашлось:
        д["точная боль"] += 1
        точных[нашлось] += 1
    else:
        д["общий дефолт"] += 1
        дефолтных[код.split(".")[0]] += 1

print("")
print("--- по отраслям книг ---")
print("   %-34s %6s %6s %6s %6s" % ("отрасль", "всего", "точно", "дефолт", "б/кода"))
for отр, д in sorted(по_отrasli.items(), key=lambda x: -x[1]["всего"]):
    print("   %-34s %6d %6d %6d %6d"
          % (отр[:34], д["всего"], д["точная боль"], д["общий дефолт"],
             д["кода нет"]))
print("")
print("--- какой станок Meyer выбирает карта градаций ---")
for с, n in станки.most_common():
    print("   %-16s %5d" % (с, n))
print("")
print("--- чаще всего боль находится по коду ---")
for к, n in точных.most_common(10):
    print("   %-8s %5d   %s" % (к, n, str((pains.get("meyer") or {}).get(к) or "")[:70]))
print("")
print("--- разделы, где точной боли НЕТ (пишем дефолтом) ---")
for к, n in дефолтных.most_common(12):
    print("   %-16s %5d" % (к, n))
print("")
print("=" * 74)
print("=== БОЛИ ОТРАСЛЕЙ ===")
print("   компаний в книгах:                  %5d" % len(компании))
print("   с кодом ОКВЭД:                      %5d" % есть_код)
print("   из них точная боль по карте:        %5d" % sum(точных.values()))
print("   пишем общим дефолтом направления:   %5d"
      % (len(компании) - sum(точных.values())))
print("   отраслей в книгах:                  %5d" % len(по_отrasli))
print("   кодов в карте Meyer:                %5d" % len(pains.get("meyer") or {}))
