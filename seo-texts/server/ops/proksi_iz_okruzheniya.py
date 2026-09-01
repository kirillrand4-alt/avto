# -*- coding: utf-8 -*-
"""Какие прокси лежат в окружении панели и живы ли они против Чеко.

Пароли не печатаем — только схема, хост и порт.
"""
import os
import re
import sqlite3
import sys
import time
import urllib.parse

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

ИМЕНА = ("PROXY_URL", "PROXY_URLV2", "PROXY_URLV3", "PROXY_URLV4",
         "MOBILE_PROXY", "MOBILE_PROXY_1", "MOBILE_PROXY_2", "MOBILE_PROXY_3",
         "HH_PROXY", "CHECKO_PROXY")

найдено = []
описания = []
for имя in ИМЕНА:
    з = os.environ.get(имя, "")
    if not з:
        continue
    try:
        u = urllib.parse.urlsplit(з if "://" in з else "http://" + з)
        описания.append("%-16s %s://%s:%s%s"
                        % (имя, u.scheme, u.hostname, u.port,
                           "  (с логином)" if u.username else ""))
        найдено.append((имя, з))
    except Exception:                                          # noqa: BLE001
        описания.append("%-16s не разобрался" % имя)

# заодно поищем файлы с прокси, где встречается «mobile»
файлы = []
for кор in (r"C:\sender", r"C:\seostat"):
    for путь, кат, имена_ф in os.walk(кор):
        кат[:] = [d for d in кат if d not in ("__pycache__", ".git", ".venv",
                                              "node_modules")]
        for имя in имена_ф:
            if re.search(r"prox|mobil", имя, re.I) and имя.endswith(
                    (".txt", ".json", ".env", ".csv")):
                файлы.append(os.path.join(путь, имя))
        if len(файлы) > 25:
            break

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
огрны = [r[0] for r in c.execute(
    "SELECT ogrn FROM requisites WHERE COALESCE(ogrn,'')<>'' "
    "  AND COALESCE(revenue_rub,'') IN ('','0') LIMIT 30")]
c.close()

итоги = []
for имя, url in найдено:
    ок, коды = 0, {}
    t0 = time.time()
    for i in range(12):
        try:
            r = requests.get("https://checko.ru/company/%s" % огрны[i % len(огрны)],
                             proxies={"http": url, "https": url},
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT "
                                                    "10.0; Win64; x64) "
                                                    "AppleWebKit/537.36"},
                             timeout=25)
            коды[r.status_code] = коды.get(r.status_code, 0) + 1
            if r.status_code == 200:
                ок += 1
        except Exception as ex:                                # noqa: BLE001
            коды[str(ex)[:20]] = коды.get(str(ex)[:20], 0) + 1
        time.sleep(0.3)
    итоги.append("%-16s ок %2d из 12 за %.0f с, коды %s"
                 % (имя, ок, time.time() - t0, коды))

print("=" * 74)
print("=== СВОДКА: ПРОКСИ ИЗ ОКРУЖЕНИЯ ПРОТИВ ЧЕКО ===")
print("найдено переменных: %d" % len(найдено))
for с in описания:
    print("   " + с)
print("")
print("файлы с прокси на дисках:")
for п in файлы[:12]:
    print("   %s" % п)
print("")
print("проба по Чеко (12 запросов на прокси):")
for с in (итоги or ["   нечего пробовать"]):
    print("   " + с)
