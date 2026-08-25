# -*- coding: utf-8 -*-
"""Соннет: 988 строк журнала с номером карточки, а карточек — 746. Почему.

Проверяем ровно две гипотезы, без догадок: строка про одно и то же письмо
записана дважды (повтор номера) и карточку потом переписала другая модель
(тот же номер под другой моделью).
"""
import io
import json
import os
import sqlite3
from collections import Counter, defaultdict

КАТАЛОГ = r"C:\sender\_ops"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
живы = {р[0] for р in c.execute("SELECT id FROM confirm_reviews")}

строк = Counter()               # модель -> строк с номером
номера = defaultdict(set)       # модель -> множество номеров
кто = defaultdict(set)          # номер -> модели
for имя in ("gen-partiya-935.jsonl", "deshevaya-partiya.jsonl"):
    п = os.path.join(КАТАЛОГ, имя)
    if not os.path.exists(п):
        continue
    for с in io.open(п, encoding="utf-8", errors="replace"):
        if not с.startswith("{"):
            continue
        try:
            з = json.loads(с)
        except Exception:  # noqa: BLE001
            continue
        rid = з.get("review_id")
        if not rid or int(rid) not in живы:
            continue
        м = (з.get("модель") or ("механика" if "deshev" in имя else "?"))
        м = м.replace("claude-", "")
        строк[м] += 1
        номера[м].add(int(rid))
        кто[int(rid)].add(м)

print("%-22s %8s %10s %10s" % ("модель", "строк", "номеров", "повторов"))
for м in sorted(строк, key=lambda x: -строк[x]):
    print("%-22s %8d %10d %10d"
          % (м, строк[м], len(номера[м]), строк[м] - len(номера[м])))

спор = {r: ms for r, ms in кто.items() if len(ms) > 1}
print("\nкарточек, за которые отчитались РАЗНЫЕ модели: %d" % len(спор))
for к, н in Counter(" + ".join(sorted(ms)) for ms in спор.values()).most_common(8):
    print("   %-46s %5d" % (к, н))
