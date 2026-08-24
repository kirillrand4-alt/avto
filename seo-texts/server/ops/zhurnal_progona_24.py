# -*- coding: utf-8 -*-
"""Есть ли в журнале прогона хоть одно сгенерированное письмо.

Ноль карточек в очереди - ещё не приговор: письмо сначала пишется в журнал
(этап «сгенерировано»), и только потом ставится в очередь. Если в журнале
пусто - значит модель не позвали ни разу, и прогон стоит на отборе.
"""
import glob
import io
import json
import os
import time
from collections import Counter

файлы = sorted(glob.glob(r"C:\sender\_ops\*.jsonl"), key=os.path.getmtime)[-4:]
for п in файлы:
    возраст = int((time.time() - os.path.getmtime(п)) // 60)
    т = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    сегодня = [с for с in т if "2026-08-24" in с]
    этапы = Counter()
    for с in т:
        try:
            этапы[json.loads(с).get("этап", "?")] += 1
        except Exception:                                          # noqa: BLE001
            этапы["не разобрано"] += 1
    print(f"{os.path.basename(п):<44} строк {len(т):>6}, из них 24.08 "
          f"{len(сегодня):>5}, обновлён {возраст} мин назад")
    print(f"    этапы: {dict(этапы.most_common(6))}")
    if сегодня:
        print(f"    последняя строка 24.08: {сегодня[-1][:170]}")
