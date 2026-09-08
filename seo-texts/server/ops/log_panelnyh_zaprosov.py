# -*- coding: utf-8 -*-
"""Настоящие запросы к панели: что просит браузер и сколько это длится."""
import glob, io, os, re, sys, time
from collections import Counter

КАНДИДАТЫ = [r"C:\sender\logs", r"C:\sender\log", r"C:\sender",
             r"C:\sender\web", r"C:\sender\_ops"]
файлы = []
for д in КАНДИДАТЫ:
    for шаб in ("*.log", "*.out", "*.txt"):
        for п in glob.glob(os.path.join(д, шаб)):
            try:
                if os.path.getmtime(п) > time.time() - 6 * 3600:
                    файлы.append(п)
            except OSError:
                pass
файлы = sorted(set(файлы), key=lambda p: -os.path.getmtime(p))[:12]
print("свежие логи (6 часов):")
for п in файлы:
    print("   %-56s %8.1f КБ  %s"
          % (п[-56:], os.path.getsize(п) / 1024.0,
             time.strftime("%H:%M", time.localtime(os.path.getmtime(п)))))

ЗАПРОС = re.compile(r'"(GET|POST) ([^" ]+)|(GET|POST) (/[^\s"]+)')
счёт = Counter()
for п in файлы:
    try:
        т = io.open(п, encoding="utf-8", errors="replace").read()[-400000:]
    except OSError:
        continue
    for м in ЗАПРОС.finditer(т):
        путь = м.group(2) or м.group(4) or ""
        if "/confirm" in путь or "/leads" in путь:
            счёт[путь.split("&")[0][:70]] += 1
print("")
print("=" * 70)
print("=== ЗАПРОСЫ К ОЧЕРЕДИ В ЛОГАХ ===")
if счёт:
    for к, в in счёт.most_common(12):
        print("   %-64s %5d" % (к, в))
else:
    print("   в логах запросов не нашлось (панель, похоже, не пишет access-лог)")
