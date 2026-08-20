# -*- coding: utf-8 -*-
"""Откуда в addr_probe взялись вердикты: разрез по source и по файлу работника.

Владелец: «проверь» — про мою фразу «вердикт скорее всего не от работника».
Догадку заменяем счётом: сколько строк с каким source, и сколько из них
есть в файле работника.
"""
import io
import json
import os
import sqlite3
from collections import Counter

Ф = r"C:\sender\_ops\probe-rezultat.jsonl"
видел = set()
if os.path.exists(Ф):
    for s in io.open(Ф, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(s)
        except Exception:                                        # noqa: BLE001
            continue
        e = str(z.get("email") or "").strip().lower()
        if e:
            видел.add(e)
print(f"адресов в файле работника: {len(видел)}")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ист = Counter()
ист_в_файле = Counter()
верд_пустых = Counter()
for r in c.execute("SELECT email, verdict, COALESCE(source,'') s FROM addr_probe"):
    s = str(r["s"]) or "(пусто)"
    ист[s] += 1
    if str(r["email"] or "").lower() in видел:
        ист_в_файле[s] += 1
    if not str(r["s"]):
        верд_пустых[str(r["verdict"])] += 1

print("\nsource -> всего строк / из них есть у работника:")
for s, n in ист.most_common():
    print(f"  {s:<14} {n:>6} / {ист_в_файле.get(s, 0):>6}")

print("\nвердикты строк с пустым source:")
for v, n in верд_пустых.most_common():
    print(f"  {v:<16} {n}")

# Колонка source появилась ALTER-ом: у строк, записанных до неё, она NULL.
# Значит «пусто» — это не «неизвестный писатель», а «старая запись».
print("\nв таблице колонки:",
      [x[1] for x in c.execute("PRAGMA table_info(addr_probe)")])
