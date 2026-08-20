# -*- coding: utf-8 -*-
"""Сколько у нас пищевых компаний под вебинар 28.08 (без КФХ).

Считаем по базе обзвона: сколько всего, у скольких есть почта, скольким
ещё не писали. Разрез по группам ОКВЭД, чтобы владелец сам решил границу
(например, включать ли напитки 11.x и оптовую торговлю едой 46.3x).
"""
import sqlite3
from collections import Counter

ОБЗВОН = r"C:\sender\obzvon-index.db"
c = sqlite3.connect("file:%s?mode=ro" % ОБЗВОН.replace("\\", "/"), uri=True)
c.row_factory = sqlite3.Row

print("== таблицы базы обзвона ==")
for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    n = c.execute(f"SELECT COUNT(*) FROM [{r['name']}]").fetchone()[0]
    print(f"  {r['name']:<22} {n}")

print("\n== колонки obzvon ==")
try:
    print("  ", [x[1] for x in c.execute("PRAGMA table_info(obzvon)")])
except Exception as ex:                                          # noqa: BLE001
    print("  не прочесть:", str(ex)[:80])
