# -*- coding: utf-8 -*-
"""Сколько компаний по коду ОКВЭД есть у чеко ВООБЩЕ (поле ЗапВсего).

Инструмент владельца: C:\\seostat\\Parser2\\metalparser\\checko.py —
api.checko.ru/v2/search, by=okved, obj=org, плюс extract_search_total.
Ключи — пул из Parser2/data/api_keys.txt (ротация, у каждого суточный лимит).

Запуск: python emkost_po_okved.py [код ...]   (без аргументов — проба на трёх)
"""
import io
import json
import os
import sys
import time

import requests

КЛЮЧИ_ФАЙЛ = r"C:\seostat\Parser2\data\api_keys.txt"
URL = "https://api.checko.ru/v2/search"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
КОДЫ = sys.argv[1:] or ["01.11.1", "46.21", "10.61.2"]

ключи = []
for с in io.open(КЛЮЧИ_ФАЙЛ, encoding="utf-8", errors="ignore"):
    с = с.strip()
    if с and not с.startswith("#"):
        ключи.append(с.split()[0])
print("ключей в файле: %d" % len(ключи))


def всего(payload):
    b = payload.get("data", payload) if isinstance(payload, dict) else {}
    if isinstance(b, dict):
        for k in ("ЗапВсего", "total", "Всего", "totalCount"):
            v = b.get(k)
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.isdigit():
                return int(v)
    return None


s = requests.Session()
s.headers.update({"User-Agent": UA})
исчерпано = 0
for код in КОДЫ:
    получилось = False
    for ключ in ключи[:40]:
        try:
            r = s.get(URL, params={"key": ключ, "by": "okved", "obj": "org",
                                   "query": код, "active": "true"}, timeout=25)
        except Exception as ex:                                    # noqa: BLE001
            continue
        if r.status_code != 200:
            continue
        try:
            п = r.json()
        except Exception:                                          # noqa: BLE001
            continue
        мет = str(п.get("meta") or п.get("Сообщение") or "")[:80]
        n = всего(п)
        if n is None:
            исчерпано += 1
            if исчерпано <= 2:
                print("   ключ не дал числа (%s): %s"
                      % (мет or r.status_code,
                         json.dumps(п, ensure_ascii=False)[:220]))
            continue
        print("%-10s ВСЕГО У ЧЕКО: %d" % (код, n))
        получилось = True
        break
        time.sleep(0.2)
    if not получилось:
        print("%-10s не удалось (проверено ключей: %d)" % (код, min(40, len(ключи))))
