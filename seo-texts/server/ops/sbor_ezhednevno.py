# -*- coding: utf-8 -*-
"""Ежедневный добор: задание в 00:15, пока не закроются все 70 кодов.

Замер сегодня: 14 живых ключей дали 207 страниц поиска (+20 081 компания) и
кончились. То есть суточная ёмкость пула ≈ 200–300 запросов, а не 1400 —
бесплатный тариф чеко считает не по сотне на ключ. Остаток добора ≈ 460
страниц, это ещё два-три захода. Руками их не сторожим: вешаем задание на
каждый день, оно само упрётся в лимит и само продолжит завтра.
"""
import csv
import io
import json
import os
import subprocess
import sys
import time
from collections import Counter

КАТИТЬ = "--katit" in sys.argv
ИМЯ = "AgroOkvedCollectDaily"
РАЗОВОЕ = "AgroOkvedCollectOnce"
КОРЕНЬ = r"C:\seostat\Parser2"
BAT = r"C:\sender\_ops\sbor-agro.cmd"
CSV_ = os.path.join(КОРЕНЬ, "data", "agro-base.csv")
ПРОГРЕСС = os.path.join(КОРЕНЬ, "data", "agro-base.progress.json")
КОДЫ = os.path.join(КОРЕНЬ, "data", "okved-agro.txt")
ЁМКОСТЬ = r"C:\sender\_ops\checko-emkost.json"

print("время на сервере: %s" % time.strftime("%d.%m.%Y %H:%M:%S"))
задание = [с.strip() for с in io.open(КОДЫ, encoding="utf-8") if с.strip()]
пройдено = set((json.load(io.open(ПРОГРЕСС, encoding="utf-8"))
                or {}).get("done_codes") or [])
ёмк = json.load(io.open(ЁМКОСТЬ, encoding="utf-8")) if os.path.exists(ЁМКОСТЬ) else {}

собрано, всего_строк = Counter(), 0
with io.open(CSV_, encoding="utf-8-sig", errors="ignore", newline="") as f:
    for ряд in csv.DictReader(f, delimiter=";"):
        к = str(ряд.get("Основной ОКВЭД") or "").strip()
        if к:
            собрано[к.split()[0]] += 1
        всего_строк += 1

осталось, страниц = 0, 0
недобор = []
for код in задание:
    e = ёмк.get(код)
    if not e:
        continue
    н = max(0, e["vsego"] - собрано.get(код, 0))
    if код in пройдено or н <= 0:
        continue
    осталось += н
    страниц += (н + 99) // 100
    недобор.append((н, код))
недобор.sort(reverse=True)

if КАТИТЬ:
    subprocess.run(["schtasks", "/Delete", "/TN", РАЗОВОЕ, "/F"],
                   capture_output=True, text=True, timeout=60)
    subprocess.run(["schtasks", "/Delete", "/TN", ИМЯ, "/F"],
                   capture_output=True, text=True, timeout=60)
    r = subprocess.run(["schtasks", "/Create", "/TN", ИМЯ, "/SC", "DAILY",
                        "/ST", "00:15", "/RU", "SYSTEM", "/RL", "HIGHEST",
                        "/F", "/TR", BAT], capture_output=True, text=True,
                       timeout=60)
    печать = ((r.stdout or "") + (r.stderr or "")).strip()[:110]
else:
    печать = "[сухой прогон] с --katit заведу ежедневное задание"

print("\n=== СОСТОЯНИЕ ПОСЛЕ СЕГОДНЯШНЕГО ЗАХОДА ===")
print("строк в agro-base.csv: %d" % всего_строк)
print("кодов пройдено полностью: %d из %d" % (len(пройдено & set(задание)),
                                              len(задание)))
print("\nчто осталось добрать (топ-15):")
for н, код in недобор[:15]:
    print("   %-10s %7d из %7d" % (код, н, ёмк[код]["vsego"]))
print("   … всего кодов с недобором: %d" % len(недобор))
print("\nостаток: %d компаний ≈ %d страниц поиска" % (осталось, страниц))
print("при сегодняшних 207 страницах в сутки — это ещё %.1f захода"
      % (страниц / 207.0))
print("\nежедневное задание %s в 00:15: %s" % (ИМЯ, печать))
