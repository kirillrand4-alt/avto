# -*- coding: utf-8 -*-
"""Правда ли новый текст лёг В ОЧЕРЕДЬ, а не остался в журнале.

Вопрос владельца прямой: «обновил письма в очереди?». Проверяем не по коду
перегенерации, а по самой очереди: сверяем текст строки с тем, что журнал
записал как «было». Совпал - значит не обновилось.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

Ж = r"C:\sender\_ops\peregeneraciya-meyer.jsonl"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

записи = {}
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("ок"):
        записи[int(z["id"])] = z

итог = Counter()
примеры = []
for rid, z in записи.items():
    строка = store.confirm_get(int(rid)) or {}
    сейчас = (строка.get("body") or "").strip()
    было = (z.get("тело_до") or "").strip()
    if not сейчас:
        итог["письма в очереди нет"] += 1
    elif сейчас[:400] == было[:400]:
        итог["текст ТОТ ЖЕ - не обновилось"] += 1
        if len(примеры) < 3:
            примеры.append(rid)
    else:
        итог["текст обновлён"] += 1
    итог[f"статус строки: {строка.get('status')}"] += 1

print(f"переписанных по журналу: {len(записи)}")
for k, n in итог.most_common():
    print(f"  {n:>4}  {k}")
if примеры:
    print("не обновились:", примеры)
