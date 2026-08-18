# -*- coding: utf-8 -*-
"""Сколько входа последнего прогона прочиталось из кэша, а сколько записано.

Проверка, что починка кэша работает не в пробирке, а на живом прогоне.
"""
import io
import json
from collections import Counter

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
строки = []
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") == "итог" or "цена_$" in z:
        строки.append(z)
хвост = строки[-10:]
c = Counter()
for z in хвост:
    c["чтение"] += int(z.get("вход_кэш_чтение") or 0)
    c["запись"] += int(z.get("вход_кэш_запись") or 0)
    c["цена"] += float(z.get("цена_$") or 0)
    c["вызовов"] += int(z.get("вызовов") or 0) + int(
        z.get("вызовов_проверок") or 0)
print(f"последних записей: {len(хвост)}")
print(f"  вызовов:        {c['вызовов']}")
print(f"  кэш прочитано:  {c['чтение']} токенов")
print(f"  кэш записано:   {c['запись']} токенов")
print(f"  цена по журналу: ${c['цена']:.2f}")
доля = c["чтение"] / max(1, c["чтение"] + c["запись"]) * 100
print(f"  доля чтения:    {доля:.0f}% (если 0 - кэш не работает)")
