# -*- coding: utf-8 -*-
"""Только чтение: разбор журнала партии по Meyer. Ничего не меняет."""
import io
import json
import os
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
строки = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            строки.append(json.loads(s))
        except Exception:
            pass
print("=== ПОЛЯ ЗАПИСИ ===")
if строки:
    print("  первая:", sorted(строки[0].keys()))
    print("  последняя:", sorted(строки[-1].keys()))
    врем = [k for k in строки[-1] if any(t in k.lower()
            for t in ("когда", "ts", "врем", "дата", "time", "at"))]
    print("  поля времени:", врем)

m = [z for z in строки if str(z.get("направление")) == "meyer"
     and z.get("этап") != "итог"]
print("\n=== MEYER: %d строк ===" % len(m))
ок = [z for z in m if z.get("ок")]
print("  годных %d (%.0f%%), брака %d" % (len(ок), 100.0 * len(ок) / max(1, len(m)),
                                          len(m) - len(ок)))
print("  потрачено $%.2f, на годное $%.3f"
      % (sum(float(z.get("цена_$") or 0) for z in m),
         sum(float(z.get("цена_$") or 0) for z in m) / max(1, len(ок))))
сек = [float(z.get("сек") or 0) for z in m if z.get("сек")]
if сек:
    сек.sort()
    print("  секунд на письмо: медиана %.0f, 10-90%% %.0f-%.0f"
          % (сек[len(сек) // 2], сек[len(сек) // 10], сек[-max(1, len(сек) // 10)]))
print("  модели:", dict(Counter(str(z.get("модель")) for z in m)))

print("\n=== ПРИЧИНЫ БРАКА (топ-15) ===")
бр = Counter()
for z in m:
    b = z.get("брак")
    if not b:
        continue
    t = b if isinstance(b, str) else json.dumps(b, ensure_ascii=False)
    бр[t[:78]] += 1
for k, v in бр.most_common(15):
    print("  %4d  %s" % (v, k))

print("\n=== ХВОСТ ЖУРНАЛА: последние 400 строк meyer ===")
х = m[-400:]
окх = sum(1 for z in х if z.get("ок"))
print("  обработано %d, годных %d (%.0f%%), $%.2f, на годное $%.3f"
      % (len(х), окх, 100.0 * окх / max(1, len(х)),
         sum(float(z.get("цена_$") or 0) for z in х),
         sum(float(z.get("цена_$") or 0) for z in х) / max(1, окх)))
