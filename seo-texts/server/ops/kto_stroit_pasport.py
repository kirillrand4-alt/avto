# -*- coding: utf-8 -*-
"""Кто и чем строит паспорт сайта: модель, объём, свежесть.

Нужно для описания смежной сессии: прежде чем просить починить признак_КЦ,
надо знать, чем он считается и во что это обходится.
"""
import json
import sqlite3
from collections import Counter

con = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True, timeout=15)
имена = [c[1] for c in con.execute("PRAGMA table_info(site_facts)")]
print("колонки site_facts:", имена)
n = con.execute("SELECT COUNT(*) FROM site_facts").fetchone()[0]
print("строк:", n)

# что лежит в служебных колонках
for к in имена:
    if к in ("inn", "facts_json"):
        continue
    try:
        проба = con.execute(
            f"SELECT {к} FROM site_facts WHERE {к} IS NOT NULL "
            f"AND TRIM(CAST({к} AS TEXT))<>'' LIMIT 3").fetchall()
        print(f"  {к}: {[str(x[0])[:90] for x in проба]}")
    except Exception as ex:                                      # noqa: BLE001
        print(f"  {к}: {str(ex)[:60]}")

print("\n== из чего складывается разбор_КЦ ==")
пример = None
кл = Counter()
for (j,) in con.execute("SELECT facts_json FROM site_facts LIMIT 3000"):
    try:
        d = json.loads(j)
    except Exception:                                            # noqa: BLE001
        continue
    рк = d.get("разбор_КЦ")
    if isinstance(рк, dict):
        for k in рк:
            кл[k] += 1
        if пример is None and рк.get("признак_КЦ"):
            пример = (d.get("цитата"), рк)
print("  поля:", dict(кл))
if пример:
    print(f"\n  пример с признаком:\n    цитата: {str(пример[0])[:120]}")
    print(f"    разбор: {json.dumps(пример[1], ensure_ascii=False)[:400]}")
con.close()
