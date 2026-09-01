# -*- coding: utf-8 -*-
"""Живая проба ходилки: работают ли прокси и отдаёт ли чеко выручку сегодня.

Берём три ОГРН прямо из сбора по Чеко (те самые, что ещё не заведены) и
пробуем достать по ним карточку теми же socks5-прокси, что использует
checko_finansy.py. Ничего не пишем — только смотрим. Сводка в конце.
"""
import csv
import io
import os
import re
import sys
import time

sys.path.insert(0, r"C:\sender\server\ops")
sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

ПРОКСИ_ФАЙЛ = r"C:\sender\dolphin-proxies.txt"
CSV = r"C:\seostat\Parser2\data\agro-base.csv"

# берём разбор из самой ходилки, чтобы мерить ЕЁ, а не свой парсер
import importlib.util                                          # noqa: E402
спец = importlib.util.spec_from_file_location(
    "checko_finansy", r"C:\sender\server\ops\checko_finansy.py")
модуль = importlib.util.module_from_spec(спец)
разобрать = None
try:
    спец.loader.exec_module(модуль)
    разобрать = getattr(модуль, "разобрать", None)
    ПРОКСИ = getattr(модуль, "прокси")()
except Exception as ex:                                        # noqa: BLE001
    ПРОКСИ = []
    печать_ошибки = str(ex)[:200]

образцы = []
with io.open(CSV, encoding="utf-8-sig", errors="replace", newline="") as ф:
    for р in csv.DictReader(ф, delimiter=";"):
        о = str(р.get("ОГРН") or "").strip()
        и = str(р.get("ИНН") or "").strip()
        н = str(р.get("Название") or "").strip()
        к = str(р.get("Основной ОКВЭД") or "").strip()
        if о and к.startswith("10."):
            образцы.append((и, о, н, к))
        if len(образцы) >= 3:
            break

итог = []
итог.append("прокси загружено: %d" % len(ПРОКСИ))
итог.append("разбор из ходилки: %s"
            % ("взят" if разобрать else "НЕ взят — модуль не загрузился"))
if not ПРОКСИ:
    итог.append("прокси не загрузились: %s" % locals().get("печать_ошибки", "?"))

for i, (инн, огрн, имя, код) in enumerate(образцы):
    if not ПРОКСИ:
        break
    px = ПРОКСИ[i % len(ПРОКСИ)]
    t0 = time.time()
    try:
        r = requests.get("https://checko.ru/company/%s" % огрн,
                         proxies={"http": px, "https": px},
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; "
                                                "Win64; x64) AppleWebKit/537.36"},
                         timeout=30)
        код_отв = r.status_code
        разбор = {}
        if код_отв == 200 and разобрать:
            try:
                разбор = разобрать(r.text) or {}
            except Exception as ex:                            # noqa: BLE001
                разбор = {"ошибка разбора": str(ex)[:60]}
        итог.append("")
        итог.append("%s  ОГРН %s  ОКВЭД %s" % (имя[:40], огрн, код))
        итог.append("   код ответа %s, %.1fс, страница %d Б"
                    % (код_отв, time.time() - t0, len(r.text or "")))
        if разбор:
            for к, v in list(разбор.items())[:8]:
                итог.append("      %-22s %s" % (к, str(v)[:60]))
        elif код_отв == 200:
            итог.append("      разбор пуст")
    except Exception as ex:                                    # noqa: BLE001
        итог.append("")
        итог.append("%s  ОГРН %s" % (имя[:40], огрн))
        итог.append("   ОШИБКА СВЯЗИ: %s" % str(ex)[:120])

print("=" * 68)
print("=== СВОДКА: ЖИВА ЛИ ХОДИЛКА СЕГОДНЯ ===")
for с in итог:
    print(с)
