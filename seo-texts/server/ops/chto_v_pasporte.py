# -*- coding: utf-8 -*-
"""Что на самом деле лежит в паспорте сайта — и у скольких компаний он есть.

Владелец поправил меня: «как не делали? а кто составлял паспорт сайта?».
Проверяю, насколько паспорт покрывает базу и что в нём.
"""
import json
import os
import sqlite3
import sys
from collections import Counter

БАЗА = r"C:\sender\enrich.db"
if not os.path.exists(БАЗА):
    print("нет enrich.db"); raise SystemExit(1)
con = sqlite3.connect(f"file:{БАЗА}?mode=ro", uri=True, timeout=10)

всего = con.execute("SELECT COUNT(*) FROM site_facts").fetchone()[0]
непустых = con.execute(
    "SELECT COUNT(*) FROM site_facts WHERE facts_json IS NOT NULL "
    "AND TRIM(facts_json) NOT IN ('', '{}')").fetchone()[0]
print(f"строк в site_facts: {всего}, с непустым паспортом: {непустых}")

ключи = Counter()
примеры = {}
for (j,) in con.execute(
        "SELECT facts_json FROM site_facts WHERE facts_json IS NOT NULL "
        "LIMIT 4000"):
    try:
        d = json.loads(j)
    except Exception:                                                  # noqa: BLE001
        continue
    if not isinstance(d, dict):
        continue
    for k, v in d.items():
        if v in (None, "", [], {}):
            continue
        ключи[k] += 1
        if k not in примеры:
            примеры[k] = json.dumps(v, ensure_ascii=False)[:110]

print("\n== из чего состоит паспорт (по 4000 строкам) ==")
for k, n in ключи.most_common(18):
    print(f"  {n:>5}  {k:<22} {примеры.get(k,'')}")

print("\n== есть ли текст сайта отдельно ==")
for табл in ("site_text", "site_pages", "sites"):
    try:
        n = con.execute(f"SELECT COUNT(*) FROM {табл}").fetchone()[0]
        print(f"  {табл}: {n} строк")
    except Exception:                                                  # noqa: BLE001
        pass
con.close()
