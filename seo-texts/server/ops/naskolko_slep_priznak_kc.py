# -*- coding: utf-8 -*-
"""Насколько слеп признак_КЦ в паспорте сайта.

Разбор «СК Дорожник-2» показал: асфальтобетонный завод со своим парком
спецтехники и ямочным ремонтом (где карту продувают сжатым воздухом перед
битумом) помечен признак_КЦ=false. Паспорт ищет явные слова про воздух и
газы, а компании их не пишут: компрессор для них инструмент, а не товар.

Если признак стоит false почти у всех, строить на нём отбор нельзя.
"""
import json
import os
import sqlite3
from collections import Counter

БАЗА = r"C:\sender\enrich.db"
con = sqlite3.connect(f"file:{БАЗА}?mode=ro", uri=True, timeout=15)

всего = верных = 0
счёт = Counter()
примеры_да = []
for (j,) in con.execute(
        "SELECT facts_json FROM site_facts WHERE facts_json IS NOT NULL"):
    try:
        d = json.loads(j)
    except Exception:                                            # noqa: BLE001
        continue
    if not isinstance(d, dict):
        continue
    рк = d.get("разбор_КЦ")
    if not isinstance(рк, dict):
        счёт["разбора КЦ нет вовсе"] += 1
        continue
    всего += 1
    if рк.get("признак_КЦ"):
        верных += 1
        счёт["признак_КЦ = TRUE"] += 1
        if len(примеры_да) < 5:
            примеры_да.append(str(d.get("цитата") or "")[:90])
    else:
        счёт["признак_КЦ = false"] += 1
    for k in ("воздух_точно", "газы_технические"):
        if рк.get(k):
            счёт[f"есть {k}"] += 1

print(f"паспортов с разбором КЦ: {всего}")
for k, n in счёт.most_common():
    доля = f" ({n/max(1,всего)*100:.1f}%)" if всего else ""
    print(f"  {n:>6}  {k}{доля}")
print(f"\nпризнак_КЦ стоит у {верных} из {всего} "
      f"({верных/max(1,всего)*100:.1f}%)")
print("\nпримеры, где признак ЕСТЬ:")
for ц in примеры_да:
    print(f"  {ц}")
con.close()
