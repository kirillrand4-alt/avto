# -*- coding: utf-8 -*-
"""Отказы модели («I can't…») в журнале 9000: цена, повторяемость по компании."""
import io
import json
from collections import Counter, defaultdict
по_комп = defaultdict(list)
цена = []
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    отказ = "I can" in json.dumps(z.get("брак") or [], ensure_ascii=False)
    по_комп[z.get("inn") or z.get("имя")].append((z.get("день"), отказ, bool(z.get("ок")), z.get("имя"), z.get("сегмент") or z.get("отрасль")))
    if отказ:
        ст = 0.0
        for к, v in z.items():
            if "цена" in к or "стоим" in к or к in ("usd", "$"):
                try:
                    ст = float(v)
                except Exception:  # noqa: BLE001
                    pass
        цена.append(ст)
всего_отк = sum(1 for v in по_комп.values() for x in v if x[1])
комп_с_отк = [k for k, v in по_комп.items() if any(x[1] for x in v)]
повтор = [k for k in комп_с_отк if sum(1 for x in по_комп[k] if x[1]) > 1]
потом_ок = [k for k in комп_с_отк if any(x[2] for x in по_комп[k])]
print("отказов всего: %d, компаний: %d, отказали >1 раза: %d, потом всё же ОК: %d"
      % (всего_отк, len(комп_с_отк), len(повтор), len(потом_ок)))
print("цена отказа (по полю журнала): среднее $%.3f" % (sum(цена) / len(цена) if цена else 0))
print("ключи записи: %s" % ",".join(sorted({к for v in [json.loads(с) for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace").read().splitlines()[-3:]] for к in v})))
дни = Counter(x[0] for v in по_комп.values() for x in v if x[1])
print("по дням: %s" % dict(дни))
for k in комп_с_отк[-12:]:
    print("   %s | попыток %d | отказов %d | ок %s" % (по_комп[k][-1][3], len(по_комп[k]),
          sum(1 for x in по_комп[k] if x[1]), any(x[2] for x in по_комп[k])))
print("=== ОТКАЗЫ ===")
