# -*- coding: utf-8 -*-
"""Список кодов под добор — без запросов к чеко.

Правило: код берём, если у нас есть покупатели (порог 5) И в базе обзвона по
этому коду меньше 500 компаний. Второе условие отсекает металлообработку,
строительство и НИР — те коды база уже выбрала, там добирать нечего, а
покупателей в них единицы.

Ёмкость рынка по каждому коду НЕ спрашиваем: разведочный прогон сжёг ключи и
измерил лишь 23 кода из 70. Сборщик всё равно ходит по страницам сам и умеет
докачку через суточный лимит.
"""
import io
import os
import sqlite3
import sys
from collections import Counter

ПОРОГ_ПОКУП = 5
ПОТОЛОК_БАЗЫ = 500
ПИСАТЬ = "--zapisat" in sys.argv
ФАЙЛ = r"C:\seostat\Parser2\data\okved-agro.txt"


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def код(з):
    з = str(з or "").strip()
    if not з or not з[0].isdigit():
        return ""
    к = з.split()[0].strip().rstrip(".,;")
    return к if к and к[0].isdigit() else ""


c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
сделки = {цифры(r[0]) for r in c.execute(
    "SELECT value FROM suppression WHERE reason='deal_in_progress' "
    "  AND scope='inn'")}
сделки.discard("")
c.close()
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
e.row_factory = sqlite3.Row
кодп, статус = {}, {}
for r in e.execute("SELECT inn, okved_main, status FROM requisites "
                   " WHERE COALESCE(ogrn,'')<>''"):
    и = цифры(r["inn"])
    if и:
        кодп[и] = код(r["okved_main"])
        статус[и] = str(r["status"] or "")
for r in e.execute("SELECT inn, okved FROM companies"):
    и = цифры(r["inn"])
    if и and not кодп.get(и):
        кодп[и] = код(r["okved"])
e.close()
пок = Counter(кодп[и] for и in сделки
              if кодп.get(и) and статус.get(и, "ACTIVE") == "ACTIVE")
o = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db", uri=True,
                    timeout=60)
баз = Counter()
for r in o.execute("SELECT okved_main FROM obzvon"):
    к = код(r[0])
    if к:
        баз[к] += 1
o.close()

брать, отсев = [], []
for к, n in пок.most_common():
    if n < ПОРОГ_ПОКУП:
        continue
    if баз.get(к, 0) >= ПОТОЛОК_БАЗЫ:
        отсев.append((к, n, баз[к]))
    else:
        брать.append((к, n, баз.get(к, 0)))
покрыто = sum(n for _, n, _ in брать)
всего_пок = sum(пок.values())
print("кодов под добор: %d — покрывают %d покупателей из %d (%.0f%%)"
      % (len(брать), покрыто, всего_пок, 100.0 * покрыто / всего_пок))
print("\n%-10s %8s %9s" % ("ОКВЭД", "покуп.", "в базе"))
for к, n, б in брать[:40]:
    print("%-10s %8d %9d" % (к, n, б))
if len(брать) > 40:
    print("   … и ещё %d кодов" % (len(брать) - 40))
print("\nотсеяно (база уже выбрала рынок): %d кодов — %s"
      % (len(отсев), ", ".join("%s (%d в базе)" % (к, б)
                               for к, _, б in отсев[:8])))
if ПИСАТЬ:
    with io.open(ФАЙЛ, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(к for к, _, _ in брать) + "\n")
        f.flush()
        os.fsync(f.fileno())
    print("\nсписок записан: %s (%d кодов)" % (ФАЙЛ, len(брать)))
else:
    print("\n(с --zapisat запишу в %s)" % ФАЙЛ)
