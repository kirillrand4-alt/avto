# -*- coding: utf-8 -*-
"""Вернуть в пул компании, на которых модель отказывалась писать (до 14.10):
по строке «отмена_попытки» на каждую такую попытку (журнал не правим, дописываем)."""
import io
import json
import os
import sys
from collections import Counter
ПРИМЕНИТЬ = "--primenit" in sys.argv
ЖУРНАЛ = r"C:\sender\_ops\gen-rossiya-9000.jsonl"
отмены = Counter()
видели = set()
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if z.get("этап") in ("итог", "отмена_попытки") or str(z.get("день") or "") >= "2026-10-14":
        continue
    б = json.dumps(z.get("брак") or [], ensure_ascii=False)
    if z.get("ок") or "I can" not in б:
        continue
    к = (z.get("recipient_id"), z.get("сек"), z.get("цена_$"))
    if к in видели:
        continue
    видели.add(к)
    отмены[str(z.get("inn"))] += 1
print("компаний %d, попыток к отмене %d" % (len(отмены), sum(отмены.values())))
if ПРИМЕНИТЬ:
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
        for инн, n in отмены.items():
            for _ in range(n):
                ж.write(json.dumps({"этап": "отмена_попытки", "inn": инн,
                                    "почему": "отказ модели до 14.10, опыт: модель пишет"}, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
print("=== ВЕРНУТЬ ОТКАЗАВШИХ: %s ===" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон"))
