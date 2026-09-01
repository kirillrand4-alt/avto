# -*- coding: utf-8 -*-
"""404 из-за адреса или из-за самих ОГРН: старые строки против свежезалитых."""
import io
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

прокси = None
with open(r"C:\sender\proxies-mobile.txt", encoding="utf-8",
          errors="replace") as ф:
    for l in ф.read().splitlines():
        if l.strip() and not l.startswith("#"):
            прокси = l.strip()
            break

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
старые = [dict(r) for r in c.execute(
    "SELECT inn, ogrn, name_short, src FROM requisites "
    " WHERE COALESCE(ogrn,'')<>'' AND src<>'checko-sbor-agro' LIMIT 3")]
новые = [dict(r) for r in c.execute(
    "SELECT inn, ogrn, name_short, src FROM requisites "
    " WHERE COALESCE(ogrn,'')<>'' AND src='checko-sbor-agro' LIMIT 3")]
c.close()


def тянуть(огрн):
    try:
        r = requests.get("https://checko.ru/company/%s" % огрн,
                         proxies={"http": прокси, "https": прокси},
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0;"
                                                " Win64; x64) AppleWebKit/537.36"},
                         timeout=25)
        return "код %s, %d Б" % (r.status_code, len(r.text or ""))
    except Exception as ex:                                    # noqa: BLE001
        return "ошибка: %s" % str(ex)[:50]


итоги = []
for метка, ряд in (("СТАРЫЕ (dadata)", старые), ("НОВЫЕ (сбор Чеко)", новые)):
    for р in ряд:
        итоги.append("%-18s ОГРН %-15s (%2d знаков) %-28s %s"
                     % (метка, р["ogrn"], len(str(р["ogrn"] or "")),
                        str(р["name_short"] or "")[:28], тянуть(р["ogrn"])))
        time.sleep(1)

print("=" * 84)
print("=== СВОДКА: СТАРЫЕ ОГРН ПРОТИВ НОВЫХ, ОДИН И ТОТ ЖЕ ПРОКСИ ===")
for с in итоги:
    print("   " + с)
