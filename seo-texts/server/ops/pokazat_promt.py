# -*- coding: utf-8 -*-
"""Показать один промпт письма из promty10.json - целиком или частями.

Промпт ~28 тысяч знаков, а хвост stdout задания ограничен. Поэтому даём
резать на части: pokazat_promt.py N [часть] [размер_части].
Без части печатаем весь; агент сам решит, нужны ли куски.
"""
import io
import json
import sys

н = int(sys.argv[1]) if len(sys.argv) > 1 else 0
часть = int(sys.argv[2]) if len(sys.argv) > 2 else 0
размер = int(sys.argv[3]) if len(sys.argv) > 3 else 12000

данные = json.load(io.open(r"C:\sender\_ops\promty10.json",
                           encoding="utf-8"))
if н >= len(данные):
    print(f"нет промпта №{н}, всего {len(данные)}")
    raise SystemExit(0)
з = данные[н]
т = з["promt"]
всего_частей = (len(т) + размер - 1) // размер
print(f"### ПРОМПТ {н}: {з['company']} | {з['email']} | ИНН {з['inn']}")
print(f"### знаков {len(т)}, частей по {размер}: {всего_частей}")
if часть:
    к = часть - 1
    print(f"### ЧАСТЬ {часть} из {всего_частей}")
    print(т[к * размер:(к + 1) * размер])
else:
    print(т)
