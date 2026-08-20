# -*- coding: utf-8 -*-
"""Тексты писем, написанных названной моделью: смотрим глазами."""
import io
import json
import sys

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
МОДЕЛЬ = next((a for a in sys.argv[1:] if not a.isdigit()), "deepseek-v4-flash")
СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "3"))

свои = []
for s in io.open(Ж, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") == "итог" and str(z.get("модель")) == МОДЕЛЬ:
        свои.append(z)
print(f"писем модели {МОДЕЛЬ}: {len(свои)}")
for z in свои[-СКОЛЬКО:]:
    print("=" * 74)
    б = z.get("брак") or []
    print(f"{z.get('имя')} | ок={z.get('ок')} | ${z.get('цена_$')}")
    print(f"брак: {'; '.join(map(str, б))[:200]}")
    print(f"ТЕМА: {z.get('тема') or z.get('тема_брака')}")
    print((z.get("тело") or z.get("тело_брака") or "(текста нет)")[:1400])
