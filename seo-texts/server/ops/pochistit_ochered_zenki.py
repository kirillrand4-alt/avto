# -*- coding: utf-8 -*-
"""Оставить в очереди зенки только мейеровские (свежий агро-сбор).

Владелец 03.09: «нужны только для мейера». Я залил 1488 сайтов из журнала
ходилки, не отделив свежий сбор от старых строк базы, — туда попали
нефтяники и прочие компании старой базы. Снимаем ТОЛЬКО те строки, которые
дописал я (по ИНН из журнала ходилки и отсутствию в otdano.txt на момент
заливки); чужие строки очереди не трогаем.

По умолчанию СУХОЙ ПРОГОН. Запуск: python pochistit_ochered_zenki.py [--primenit]
"""
import io
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import Counter

ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"
ОЧЕРЕДЬ = r"C:\seostat\drop\zenno\ochered.txt"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
свежие = {цифры(r[0]) for r in c.execute(
    "SELECT inn FROM requisites WHERE src='checko-sbor-agro'")}
c.close()

# ИНН, которые вообще есть в журнале ходилки с сайтом
из_ходилки = set()
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    if z.get("сбой") or not str(z.get("site_checko") or "").strip():
        continue
    и = цифры(z.get("inn"))
    if и:
        из_ходилки.add(и)

строки = io.open(ОЧЕРЕДЬ, encoding="utf-8", errors="replace").read().splitlines()
оставить, снять = [], []
счёт = Counter()
for с in строки:
    if not с.strip():
        continue
    инн = цифры(с.split(";")[0])
    if инн in из_ходилки and инн not in свежие:
        снять.append(с)
        счёт["моя заливка, НЕ мейер — снимаю"] += 1
    else:
        оставить.append(с)
        if инн in свежие:
            счёт["мейеровские — оставляю"] += 1
        else:
            счёт["чужие строки очереди — не трогаю"] += 1

if ПРИМЕНИТЬ and снять:
    бэкап = ОЧЕРЕДЬ + ".bak-%d" % int(time.time())
    shutil.copy2(ОЧЕРЕДЬ, бэкап)
    with io.open(ОЧЕРЕДЬ, "w", encoding="utf-8", newline="\n") as ф:
        ф.write("\n".join(оставить) + ("\n" if оставить else ""))
        ф.flush()
        os.fsync(ф.fileno())

сейчас = len([с for с in io.open(ОЧЕРЕДЬ, encoding="utf-8",
                                 errors="replace") if с.strip()])

print("=" * 76)
print("=== СВОДКА: ЧИСТКА ОЧЕРЕДИ ЗЕНКИ ===")
print("режим: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("")
print("было строк в очереди: %d" % len(строки))
for к, в in счёт.most_common():
    print("   %-34s %6d" % (к, в))
print("")
print("строк в очереди сейчас: %d" % сейчас)
print("")
print("примеры снимаемых:")
for с in снять[:5]:
    print("   " + с[:80])
