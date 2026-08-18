# -*- coding: utf-8 -*-
"""Из чего складывается цена письма: модель, токены входа/выхода, попытки.

Дешевить наугад нельзя: у письма три статьи расхода — сколько мыШЛЁМ в
промпте, сколько модель ПИШЕТ в ответ и сколько раз мы это повторяем из-за
брака. Считаем каждую по журналу партии.
"""
import io
import json
import os
from collections import Counter

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
поля = Counter()
модели = Counter()
вход = []
выход = []
попыток = Counter()
удач = 0
всего = 0
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") in ("итог", "отмена_попытки"):
        continue
    всего += 1
    if z.get("ок"):
        удач += 1
    inn = str(z.get("inn") or "")
    if inn:
        попыток[inn] += 1
    for k in z:
        поля[k] += 1
    u = z.get("usage") or z.get("токены") or {}
    if isinstance(u, dict):
        if u.get("input_tokens"):
            вход.append(int(u["input_tokens"]))
        if u.get("output_tokens"):
            выход.append(int(u["output_tokens"]))
    м = z.get("модель") or z.get("model") or (u.get("model") if isinstance(u, dict) else "")
    if м:
        модели[str(м)] += 1

print(f"строк генерации: {всего}, удачных: {удач}")
print("поля записи:", dict(поля.most_common(14)))
print("модели:", dict(модели.most_common()))
if вход:
    вход.sort(); выход.sort()
    print(f"вход  токенов: медиана {вход[len(вход)//2]}, "
          f"макс {вход[-1]}, записей {len(вход)}")
    print(f"выход токенов: медиана {выход[len(выход)//2] if выход else 0}, "
          f"макс {выход[-1] if выход else 0}")
else:
    print("токенов в журнале нет — цену считали иначе")
р = Counter(попыток.values())
print("\nсколько попыток пришлось на компанию:")
for k in sorted(р):
    print(f"  {k} попыт.: {р[k]} компаний")
print(f"итого попыток {sum(попыток.values())} на {len(попыток)} компаний = "
      f"{sum(попыток.values())/max(1,len(попыток)):.2f} на компанию")
