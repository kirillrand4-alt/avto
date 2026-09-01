# -*- coding: utf-8 -*-
"""Один ОГРН через каждый прокси по очереди: кто отдаёт 404."""
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
огрны = [r[0] for r in c.execute(
    "SELECT ogrn FROM requisites WHERE src='checko-sbor-agro' "
    "  AND COALESCE(ogrn,'')<>'' LIMIT 2")]
c.close()

итоги = []
for н, url in enumerate(прокси, 1):
    хост = url.split("@")[-1]
    for огрн in огрны:
        for путь, метка in (("", "карточка"), ("/contacts", "контакты")):
            try:
                r = requests.get(
                    "https://checko.ru/company/%s%s" % (огрн, путь),
                    proxies={"http": url, "https": url},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; "
                                           "Win64; x64) AppleWebKit/537.36"},
                    timeout=25)
                итоги.append("%d) %-24s %-9s ОГРН %s -> код %s, %d Б"
                             % (н, хост, метка, огрн, r.status_code,
                                len(r.text or "")))
            except Exception as ex:                            # noqa: BLE001
                итоги.append("%d) %-24s %-9s ОГРН %s -> ошибка %s"
                             % (н, хост, метка, огрн, str(ex)[:44]))
            time.sleep(0.6)

print("=" * 84)
print("=== СВОДКА: КАЖДЫЙ ПРОКСИ ОТДЕЛЬНО ===")
for с in итоги:
    print("   " + с)
