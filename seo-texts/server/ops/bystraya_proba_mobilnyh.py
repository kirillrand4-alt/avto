# -*- coding: utf-8 -*-
"""Быстрая проба трёх мобильных: внешний IP и один запрос к Чеко."""
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

прокси, видели = [], set()
with open(r"C:\sender\proxies-mobile.txt", encoding="utf-8",
          errors="replace") as ф:
    for l in ф.read().splitlines():
        l = l.strip()
        if l and not l.startswith("#") and l not in видели:
            видели.add(l)
            прокси.append(l)

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
огрн = c.execute(
    "SELECT ogrn FROM requisites WHERE COALESCE(ogrn,'')<>'' LIMIT 1"
).fetchone()[0]
c.close()

итоги = []
for н, url in enumerate(прокси, 1):
    хост = url.split("@")[-1]
    ip = "?"
    t0 = time.time()
    try:
        r = requests.get("https://api.ipify.org",
                         proxies={"http": url, "https": url}, timeout=20)
        ip = r.text.strip() if r.status_code == 200 else "код %s" % r.status_code
    except Exception as ex:                                    # noqa: BLE001
        ip = "НЕ ОТВЕЧАЕТ: %s" % str(ex)[:60]
    ч = "—"
    try:
        r2 = requests.get("https://checko.ru/company/%s" % огрн,
                          proxies={"http": url, "https": url},
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0;"
                                                 " Win64; x64) AppleWebKit/537.36"},
                          timeout=25)
        ч = "код %s, %d Б" % (r2.status_code, len(r2.text or ""))
    except Exception as ex:                                    # noqa: BLE001
        ч = "ошибка: %s" % str(ex)[:60]
    итоги.append("%d) %-28s ip %-34s чеко: %s  (%.1f с)"
                 % (н, хост, ip, ч, time.time() - t0))

print("=" * 78)
print("=== СВОДКА: БЫСТРАЯ ПРОБА МОБИЛЬНЫХ ===")
print("сейчас: %s" % time.strftime("%H:%M:%S"))
for с in итоги:
    print("   " + с)
