# -*- coding: utf-8 -*-
"""Только чтение: какими моделями писался последний прогон (по журналу)."""
import io
import json
import os
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
стр = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            стр.append(json.loads(s))
        except Exception:
            pass
сег = [z for z in стр if str(z.get("день")) == "2026-08-31"
       and str(z.get("направление")) == "meyer" and z.get("этап") != "итог"]
хвост = сег[-109:]
print("=== МОДЕЛИ ПИСЬМА, последние %d строк meyer за сегодня ===" % len(хвост))
for k, v in Counter(str(z.get("модель")) for z in хвост).most_common():
    print("  %-24s %4d" % (k, v))

ок = [z for z in хвост if z.get("ок")]
print("\n=== ЦЕНА В РАЗБИВКЕ (там, где журнал её делит) ===")
цп = sum(float(z.get("цена_письма_$") or 0) for z in хвост)
цпр = sum(float(z.get("цена_проверок_$") or 0) for z in хвост)
цв = sum(float(z.get("цена_$") or 0) for z in хвост)
print("  всего        $%.2f" % цв)
print("  из них письмо $%.2f (%.0f%%)" % (цп, 100.0 * цп / max(0.01, цв)))
print("  проверки/линзы $%.2f (%.0f%%)" % (цпр, 100.0 * цпр / max(0.01, цв)))
print("  вызовов проверок: %d" % sum(int(z.get("вызовов_проверок") or 0) for z in хвост))

print("\n=== ИТОГ ===")
print("  годных: %d из %d" % (len(ок), len(хвост)))
if ок:
    print("  на годное письмо: $%.3f" % (цв / len(ок)))
    print("  из них только генерация: $%.3f" % (цп / len(ок)))
