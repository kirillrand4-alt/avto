# -*- coding: utf-8 -*-
"""own-site — это правда сайт компании, или так метится и Чеко?

Три проверки разом:
 1) какие значения source вообще бывают и сколько их;
 2) что ставит сборщик checko_contacts.py;
 3) есть ли marushkiiin@yandex.ru на странице контактов Чеко.
"""
import io
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

ПОЧТА = "marushkiiin@yandex.ru"
ОГРН = "1207800152647"

# 1) словарь источников
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
ист = Counter()
for (s,) in c.execute("SELECT source FROM emails"):
    ист[str(s or "(пусто)")] += 1
пометки = Counter()
for (p,) in c.execute("SELECT pometka FROM emails"):
    пометки[str(p or "(пусто)")] += 1
c.close()

# 2) что ставит сборщик Чеко
ставит = []
for п in (r"C:\sender\server\ops\checko_contacts.py",
          r"C:\sender\server\checko_contacts.py"):
    if os.path.exists(п):
        т = io.open(п, encoding="utf-8", errors="replace").read()
        for м in re.finditer(r"^.{0,110}(source|источник|pometka|кэш-добор)"
                             r".{0,110}$", т, re.M):
            с = м.group(0).strip()
            if с and not с.startswith("#"):
                ставит.append("%s| %s" % (os.path.basename(п), с[:140]))
        break

# где ещё в коде ставится 'own-site' и 'кэш-добор'
кто_ставит = []
for корень in (r"C:\sender\server", r"C:\sender\sender"):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", ".venv", "tests")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            ф = os.path.join(путь, имя)
            try:
                т = io.open(ф, encoding="utf-8", errors="replace").read()
            except Exception:                                  # noqa: BLE001
                continue
            for кл in ("own-site", "кэш-добор"):
                for м in re.finditer(r"^.{0,100}%s.{0,100}$" % re.escape(кл),
                                     т, re.M):
                    с = м.group(0).strip()
                    if с and not с.lstrip().startswith("#"):
                        кто_ставит.append("%s| %s" % (имя, с[:130]))

# 3) страница контактов Чеко
прокси = None
with open(r"C:\sender\proxies-mobile.txt", encoding="utf-8",
          errors="replace") as ф:
    for l in ф.read().splitlines():
        if l.strip() and not l.startswith("#"):
            прокси = l.strip()
            break
чеко = "не пробовали"
есть_там = None
почты_чеко = []
try:
    r = requests.get("https://checko.ru/company/%s/contacts" % ОГРН,
                     proxies={"http": прокси, "https": прокси},
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; "
                                            "Win64; x64) AppleWebKit/537.36"},
                     timeout=30)
    чеко = "код %s, %d Б" % (r.status_code, len(r.text or ""))
    if r.status_code == 200:
        текст = r.text
        есть_там = ПОЧТА in текст
        почты_чеко = sorted(set(re.findall(
            r"[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", текст)))[:12]
except Exception as ex:                                        # noqa: BLE001
    чеко = "ошибка: %s" % str(ex)[:70]

print("=" * 84)
print("=== СВОДКА: own-site — ЭТО САЙТ ИЛИ ЧЕКО? ===")
print("")
print("--- значения source в enrich.emails ---")
for к, в in ист.most_common(12):
    print("   %-26s %7d" % (к, в))
print("")
print("--- значения pometka ---")
for к, в in пометки.most_common(8):
    print("   %-26s %7d" % (к, в))
print("")
print("--- что ставит checko_contacts.py ---")
for с in (ставит[:8] or ["   файла нет или упоминаний не найдено"]):
    print("   " + с)
print("")
print("--- кто в коде ставит own-site / кэш-добор ---")
for с in list(dict.fromkeys(кто_ставит))[:12]:
    print("   " + с)
print("")
print("--- СТРАНИЦА КОНТАКТОВ ЧЕКО (ОГРН %s) ---" % ОГРН)
print("   ответ: %s" % чеко)
print("   искомый адрес там: %s"
      % ("ЕСТЬ" if есть_там else ("нет" if есть_там is False else "?")))
print("   почты на странице: %s" % (", ".join(почты_чеко) or "—"))
