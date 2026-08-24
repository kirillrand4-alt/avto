# -*- coding: utf-8 -*-
"""Что пишется в журнал дописанных зачинов: катим или молотим вхолостую.

В списке процессов флаг виден как «--??????» — шесть вопросов вместо
шести букв «катить». Утром такая же картина означала настоящую поломку
аргументов, поэтому проверяем, а не успокаиваем себя: wmic рисует
кириллицу вопросами из-за кодировки консоли, и это может быть просто
артефакт вывода.

Решает дело содержимое журнала. В сухом режиме скрипт выходит ДО записи,
так что свежие строки с постановкой в очередь = катит по-настоящему.
"""
import io
import json
import os
import time
from collections import Counter

Ж = r"C:\sender\_ops\dopisannye-zachiny.jsonl"
if not os.path.exists(Ж):
    print("журнала нет вовсе")
    raise SystemExit(0)

строки = io.open(Ж, encoding="utf-8", errors="replace").read().splitlines()
print("строк в журнале: %d, изменён %d с назад"
      % (len(строки), int(time.time() - os.path.getmtime(Ж))))

сегодня = time.strftime("%Y-%m-%d")
свежие, этапы, в_очередь = [], Counter(), 0
for с in строки:
    try:
        з = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    когда = str(з.get("когда") or з.get("ts") or з.get("день") or "")
    if сегодня in когда or not когда:
        свежие.append(з)
    этапы[str(з.get("этап") or з.get("итог") or "?")] += 1
    if з.get("review_id") or з.get("очередь") or з.get("ок"):
        в_очередь += 1

print("этапы по всему журналу:", dict(этапы))
print("строк с признаком постановки в очередь: %d" % в_очередь)

print("\n=== ПОСЛЕДНИЕ 6 СТРОК ===")
for с in строки[-6:]:
    try:
        з = json.loads(с)
    except Exception:                                          # noqa: BLE001
        print("  (не json):", с[:200])
        continue
    сжато = {}
    for k, v in з.items():
        if isinstance(v, str) and len(v) > 90:
            сжато[k] = v[:90] + "…"
        else:
            сжато[k] = v
    print("  " + json.dumps(сжато, ensure_ascii=False)[:520])
