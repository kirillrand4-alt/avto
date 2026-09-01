# -*- coding: utf-8 -*-
"""Что за компании ходилка берёт первыми и почему по ним 404."""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"

сделано = set()
if os.path.exists(ЖУРНАЛ):
    for с in open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        try:
            з = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        if з.get("сбой"):
            continue
        if з.get("inn"):
            сделано.add(str(з["inn"]))

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
ряды = [dict(r) for r in c.execute(
    "SELECT inn, ogrn, name_short, status, src FROM requisites "
    " WHERE COALESCE(ogrn,'')<>''")]
c.close()

цели = [r for r in ряды if str(r["inn"]) not in сделано][:6]
из_сбора = sum(1 for r in ряды if r["src"] == "checko-sbor-agro")

прокси = None
with open(r"C:\sender\proxies-mobile.txt", encoding="utf-8",
          errors="replace") as ф:
    for l in ф.read().splitlines():
        if l.strip() and not l.startswith("#"):
            прокси = l.strip()
            break

итоги = []
for р in цели:
    try:
        rr = requests.get("https://checko.ru/company/%s" % р["ogrn"],
                          proxies={"http": прокси, "https": прокси},
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0;"
                                                 " Win64; x64) AppleWebKit/537.36"},
                          timeout=25)
        ответ = "код %s, %d Б" % (rr.status_code, len(rr.text or ""))
    except Exception as ex:                                    # noqa: BLE001
        ответ = "ошибка %s" % str(ex)[:40]
    итоги.append("ИНН %-13s ОГРН %-15s src=%-18s %-24s %s"
                 % (р["inn"], р["ogrn"], str(р["src"])[:18],
                    str(р["name_short"] or "")[:24], ответ))
    time.sleep(0.8)

print("=" * 92)
print("=== СВОДКА: ПЕРВЫЕ ЦЕЛИ ХОДИЛКИ ===")
print("строк с ОГРН всего %d, из них свежего сбора %d, спрошено %d"
      % (len(ряды), из_сбора, len(сделано)))
print("")
for с in итоги:
    print("   " + с)
