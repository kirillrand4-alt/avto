# -*- coding: utf-8 -*-
"""Полный список кодов под добор + ёмкость рынка по каждому.

Берём все коды, где есть покупатели (порог 5), меряем ЗапВсего у чеко и
сравниваем с тем, что уже есть в базе обзвона. Коды, где база уже покрывает
рынок, помечаем — их добирать нечего.

Пишет список в C:\\seostat\\Parser2\\data\\okved-agro.txt (по коду в строке).
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

import requests

ПОРОГ = int(sys.argv[1]) if len(sys.argv) > 1 else 5
ПИСАТЬ = "--zapisat" in sys.argv
ФАЙЛ = r"C:\seostat\Parser2\data\okved-agro.txt"
КЛЮЧИ = r"C:\seostat\Parser2\data\api_keys.txt"
URL = "https://api.checko.ru/v2/search"


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

ключи = [с.strip().split()[0] for с in io.open(КЛЮЧИ, encoding="utf-8",
                                               errors="ignore")
         if с.strip() and not с.strip().startswith("#")]
поз = [0]
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})


def рынок(к):
    for _ in range(10):
        ключ = ключи[поз[0] % len(ключи)]
        поз[0] += 1
        try:
            r = s.get(URL, params={"key": ключ, "by": "okved", "obj": "org",
                                   "query": к, "active": "true"}, timeout=25)
        except Exception:                                          # noqa: BLE001
            continue
        if r.status_code != 200:
            continue
        try:
            б = (r.json() or {}).get("data") or {}
        except Exception:                                          # noqa: BLE001
            continue
        v = б.get("ЗапВсего")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return None


коды = [к for к, n in пок.most_common() if n >= ПОРОГ]
print("кодов с покупателями от %d: %d" % (ПОРОГ, len(коды)))
ряды = []
for к in коды:
    n = рынок(к)
    ряды.append((к, пок[к], баз.get(к, 0), n))
    time.sleep(0.1)

брать = []
print("\n%-10s %7s %8s %9s %9s  %s"
      % ("ОКВЭД", "покуп.", "в базе", "у чеко", "добрать", "решение"))
for к, п, б, рын in sorted(ряды, key=lambda x: -(x[3] or 0)):
    if рын is None:
        реш = "не измерен"
    elif б >= рын * 0.9:
        реш = "рынок выбран"
    elif рын - б < 50:
        реш = "мелочь"
    else:
        реш = "БРАТЬ"
        брать.append(к)
    print("%-10s %7d %8d %9s %9s  %s"
          % (к, п, б, рын if рын is not None else "—",
             (рын - б) if рын is not None else "—", реш))
итог = sum((р - б) for к, п, б, р in ряды
           if р is not None and к in брать)
print("\nкодов брать: %d, компаний добрать: ~%d" % (len(брать), итог))
if ПИСАТЬ:
    with io.open(ФАЙЛ, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(брать) + "\n")
        f.flush()
        os.fsync(f.fileno())
    print("список записан: %s" % ФАЙЛ)
else:
    print("(с --zapisat запишу список в %s)" % ФАЙЛ)
