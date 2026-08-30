# -*- coding: utf-8 -*-
"""Где сейчас сбор по кодам: задание, ключи, файл, сколько кодов осталось."""
import io
import os
import re
import subprocess
import csv
from collections import Counter

КОРЕНЬ = r"C:\seostat\Parser2"
КОДЫ = os.path.join(КОРЕНЬ, "data", "okved-agro.txt")
CSV = os.path.join(КОРЕНЬ, "data", "agro-base.csv")
ЛОГ = r"C:\sender\_ops\sbor-agro.log"

print("=== ФАЙЛЫ Parser2/data ===")
d = os.path.join(КОРЕНЬ, "data")
for имя in sorted(os.listdir(d)):
    п = os.path.join(d, имя)
    if os.path.isfile(п):
        print("   %-34s %10d Б  %s" % (имя, os.path.getsize(п),
              __import__("time").strftime("%d.%m %H:%M",
              __import__("time").localtime(os.path.getmtime(п)))))

print("\n=== КЛЮЧИ: ищу пул ===")
for корень, папки, файлы in os.walk(КОРЕНЬ):
    if any(х in корень for х in (".git", ".venv", "__pycache__")):
        continue
    for f in файлы:
        if re.search(r"key|klyuch|token", f, re.I):
            п = os.path.join(корень, f)
            try:
                р = os.path.getsize(п)
            except OSError:
                continue
            print("   %s  (%d Б)" % (п, р))

print("\n=== ЗАДАНИЕ ПЛАНИРОВЩИКА ===")
r = subprocess.run(["schtasks", "/Query", "/TN", "AgroOkvedCollectOnce",
                    "/V", "/FO", "LIST"], capture_output=True, text=True,
                   timeout=60)
for с in (r.stdout or "").splitlines():
    if any(к in с for к in ("Status", "Last Run", "Last Result", "Next Run")):
        print("   %s" % с.strip()[:110])
if r.returncode:
    print("   нет задания (%s)" % (r.stderr or "").strip()[:90])

r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*daily_collect*' }).Count"],
                   capture_output=True, text=True, timeout=90)
print("   живых процессов daily_collect: %s" % (r.stdout or "").strip())

print("\n=== ХВОСТ ЛОГА ===")
if os.path.exists(ЛОГ):
    строки = io.open(ЛОГ, encoding="utf-8", errors="replace").read().splitlines()
    for с in строки[-14:]:
        print("   %s" % с[:150])
else:
    print("   лога нет")

задание = [с.strip() for с in io.open(КОДЫ, encoding="utf-8")
           if с.strip()] if os.path.exists(КОДЫ) else []
собрано = Counter()
всего = 0
if os.path.exists(CSV):
    with io.open(CSV, encoding="utf-8-sig", errors="ignore", newline="") as f:
        for ряд in csv.DictReader(f, delimiter=";"):
            к = str(ряд.get("Основной ОКВЭД") or "").strip()
            собрано[к.split()[0] if к else ""] += 1
            всего += 1

print("\n=== ИТОГ ===")
print("кодов в задании: %d; строк в csv: %d" % (len(задание), всего))
готовы = [к for к in задание if собрано.get(к)]
пусто = [к for к in задание if not собрано.get(к)]
print("коды с добычей: %d, пустых: %d" % (len(готовы), len(пусто)))
print("\nсобрано по кодам задания:")
for к in задание:
    if собрано.get(к):
        print("   %-10s %6d" % (к, собрано[к]))
print("\nещё не тронуты (%d): %s" % (len(пусто), ", ".join(пусто)))
