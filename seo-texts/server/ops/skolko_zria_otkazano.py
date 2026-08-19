# -*- coding: utf-8 -*-
"""Сколько компаний линза отвергла зря — по поправкам владельца 19.08.

Он назвал два класса, отвергнутых неверно: аренда и парк спецтехники
(у арендодателя своя ремонтная база, а дорожник арендует технику и при этом
покупает компрессор) и металлопрокат с услугами резки (резка, зачистка,
обдув идут на любом металлическом переделе).

Вердикты линзы кэшируются в target_verdicts, то есть отказ живёт вечно.
Считаем, скольких это касается, прежде чем платить за пересуд.
"""
import os
import re
import sqlite3
import sys
from collections import Counter

БАЗЫ = [r"C:\sender\sender.db", r"C:\sender\enrich.db",
        r"C:\sender\obzvon-index.db"]
ВЕРНУТЬ = re.compile(
    r'(?i)(аренд\w*\s*(спец)?техник|прокат\s+техник|парк\s+спецтехник|'
    r'металлопрокат|металлобаз|услуг\w*\s+резк|резк\w*\s+металл|'
    r'торговл\w*\s+металл|металлотрейд|сортов\w*\s+прокат|трубн\w*\s+прокат)')

найдено = None
for б in БАЗЫ:
    if not os.path.exists(б):
        continue
    try:
        con = sqlite3.connect(f"file:{б}?mode=ro", uri=True, timeout=10)
        con.execute("SELECT 1 FROM target_verdicts LIMIT 1").fetchone()
        найдено = (б, con)
        break
    except Exception:                                            # noqa: BLE001
        pass
if not найдено:
    print("таблицы target_verdicts не нашёл ни в одной базе")
    raise SystemExit(1)
б, con = найдено
print(f"вердикты линзы: {б}")

всего = con.execute("SELECT COUNT(*) FROM target_verdicts").fetchone()[0]
по_вердикту = con.execute(
    "SELECT verdict, COUNT(*) FROM target_verdicts GROUP BY verdict").fetchall()
print(f"всего вердиктов: {всего} | {dict(по_вердикту)}")

вернуть = []
причины = Counter()
for инн, v, чем, почему in con.execute(
        "SELECT inn, verdict, COALESCE(chem,''), COALESCE(pochemu,'') "
        "FROM target_verdicts WHERE verdict='не покупатель'"):
    т = f"{чем} {почему}"
    if ВЕРНУТЬ.search(т):
        вернуть.append((инн, чем, почему))
        причины[ВЕРНУТЬ.search(т).group(0).lower()[:26]] += 1

print(f"\nотказов, попадающих под поправки владельца: {len(вернуть)}")
for k, n in причины.most_common(12):
    print(f"  {n:>4}  {k}")
print("\n== примеры ==")
for инн, чем, почему in вернуть[:10]:
    print(f"  {инн}: {чем} — {почему[:90]}")
con.close()
