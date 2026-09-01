# -*- coding: utf-8 -*-
"""Как ротация мобильных описана в news_scan.py + смена IP на деле.

Секреты не печатаем.
"""
import io
import re
import sys
import time

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

П = r"C:\sender\server\news_scan.py"
т = io.open(П, encoding="utf-8", errors="replace").read().splitlines()
print("=== news_scan.py вокруг строки 371 ===")
for i in range(max(0, 355), min(len(т), 400)):
    print("%4d| %s" % (i + 1, т[i][:150]))

МОБИЛЬНЫЕ = []
for l in io.open(r"C:\sender\proxies-mobile.txt", encoding="utf-8",
                 errors="replace"):
    l = l.strip()
    if l and not l.startswith("#"):
        МОБИЛЬНЫЕ.append(l)

print("")
print("=== МЕНЯЕТСЯ ЛИ IP САМ: шесть замеров через минуту ===")
итоги = []
for н, url in enumerate(МОБИЛЬНЫЕ, 1):
    адреса = []
    for _ in range(3):
        try:
            r = requests.get("https://api.ipify.org",
                             proxies={"http": url, "https": url}, timeout=20)
            адреса.append(r.text.strip() if r.status_code == 200
                          else "код %s" % r.status_code)
        except Exception as ex:                                # noqa: BLE001
            адреса.append("ошибка: %s" % str(ex)[:28])
        time.sleep(20)
    итоги.append("мобильный %d: %s" % (н, " -> ".join(адреса)))

print("")
print("=" * 74)
print("=== СВОДКА: РОТАЦИЯ IP ===")
for с in итоги:
    print("   " + с)
print("")
print("Разные адреса подряд = ротация по таймеру, значит лимит Чеко на")
print("адрес сбрасывается сам. Один и тот же = нужна ссылка смены IP.")
