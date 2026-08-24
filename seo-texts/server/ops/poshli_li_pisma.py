# -*- coding: utf-8 -*-
"""Пошли ли письма после перезапуска без предклассификатора.

Доказательство генерации - строки «сгенерировано» в журнале и карточки в
очереди, а не живой процесс. Заодно смотрим, какая модель реально в деле:
кириллические имена аргументов до сервера не доезжают, теперь передаём
латиницей (model=), и это надо подтвердить.
"""
import glob
import io
import json
import os
import sqlite3
import time
from collections import Counter

ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
строки = io.open(ж, encoding="utf-8", errors="replace").read().splitlines()
сег = [с for с in строки if "2026-08-24" in с]
print(f"журнал: {len(строки)} строк, за 24.08 — {len(сег)}, "
      f"обновлён {int((time.time()-os.path.getmtime(ж))//60)} мин назад")
этапы, модели = Counter(), Counter()
for с in сег:
    try:
        д = json.loads(с)
    except Exception:                                              # noqa: BLE001
        continue
    этапы[д.get("этап", "?")] += 1
    м = д.get("модель") or d if False else д.get("модель")
    if м:
        модели[м] += 1
print("этапы за сегодня:", dict(этапы))
print("модели за сегодня:", dict(модели))
if сег:
    print("последняя строка:", сег[-1][:200])

c = sqlite3.connect(r"C:\sender\sender.db")
н = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE "
              "substr(created_at,1,10)='2026-08-24'").fetchone()[0]
print(f"\nкарточек в очереди за 24.08: {н}")

print("\n=== логи новых прогонов ===")
# ГЛОБ БЫЛ ПРИБИТ К ЧАСУ 10 и после перезапуска в 11:22 показывал
# старые, уже снятые прогоны. Берём два самых свежих за день.
for п in sorted(glob.glob(r"C:\sender\_ops\partiya_gen-0824-*.log"),
                key=os.path.getmtime)[-2:]:
    т = io.open(п, encoding="utf-8", errors="replace").read()
    print(f"\n-- {os.path.basename(п)} ({len(т)} знаков, "
          f"{int((time.time()-os.path.getmtime(п))//60)} мин назад)")
    for с in т.splitlines()[:12]:
        print("   " + с[:150])
