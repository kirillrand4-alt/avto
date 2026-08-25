# -*- coding: utf-8 -*-
"""Сколько письмо-попыток дала каждая модель и сколько из них дошло до очереди.

Разрыв «написали 974 — в очереди 700» живёт ровно в двух местах: письмо
могло не получить карточку (гейт/линза срубили после написания) и карточка
могла быть снята позже. Первое считаем тут, второе — svedenie_kratko.
"""
import io
import json
import os
import sqlite3
from collections import Counter

КАТАЛОГ = r"C:\sender\_ops"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
живы = {р[0] for р in c.execute("SELECT id FROM confirm_reviews")}

итог = Counter()
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
        if "ок" not in з and "модель" not in з:
            continue          # строка этапа, а не результат письма
        мод = (з.get("модель") or ("механика" if "deshev" in имя else "?"))
        мод = мод.replace("claude-", "")
        rid = з.get("review_id")
        if rid and int(rid) in живы:
            итог[(мод, "карточка есть")] += 1
        elif rid:
            итог[(мод, "карточка исчезла")] += 1
        elif з.get("ок") or з.get("тело"):
            итог[(мод, "написано, но в очередь не попало")] += 1
        else:
            итог[(мод, "брак: письма не вышло")] += 1

СТОЛБЦЫ = ["карточка есть", "написано, но в очередь не попало",
           "брак: письма не вышло", "карточка исчезла"]
модели = sorted({м for м, _ in итог}, key=lambda м: -sum(
    итог[(м, с)] for с in СТОЛБЦЫ))
print("%-22s %8s | %s" % ("модель", "попыток",
                          " ".join("%34s" % с[:34] for с in СТОЛБЦЫ)))
for м in модели:
    n = sum(итог[(м, с)] for с in СТОЛБЦЫ)
    print("%-22s %8d | %s" % (м, n, " ".join("%34d" % итог[(м, с)]
                                             for с in СТОЛБЦЫ)))
