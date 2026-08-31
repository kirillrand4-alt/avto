# -*- coding: utf-8 -*-
"""Только чтение: отдача Meyer с ПРАВИЛЬНЫМ знаменателем.

Строки без модели - отсев бесплатными отсечками до генерации. Считать их
браком генерации значит занизить отдачу втрое. Ничего не меняет.
"""
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
m = [z for z in стр if str(z.get("направление")) == "meyer" and z.get("этап") != "итог"]
с_моделью = [z for z in m if z.get("модель") and str(z.get("модель")) != "None"]
без = [z for z in m if not z.get("модель") or str(z.get("модель")) == "None"]


def свод(имя, гр):
    if not гр:
        print("  %-28s пусто" % имя)
        return
    ок = [z for z in гр if z.get("ок")]
    ц = sum(float(z.get("цена_$") or 0) for z in гр)
    print("  %-28s всего %5d | годных %5d (%3.0f%%) | $%8.2f | на годное $%.3f"
          % (имя, len(гр), len(ок), 100.0 * len(ок) / len(гр), ц, ц / max(1, len(ок))))


print("=== MEYER: РАЗДЕЛЕНИЕ ПО ЗНАМЕНАТЕЛЮ ===")
свод("ВСЕ строки", m)
свод("с моделью (генерация)", с_моделью)
свод("без модели (отсев)", без)

print("\n=== строки БЕЗ модели: сколько из них с браком и цена ===")
print("  с непустым полем брак: %d" % sum(1 for z in без if z.get("брак")))
print("  с ненулевой ценой    : %d" % sum(1 for z in без if float(z.get("цена_$") or 0) > 0))
print("  ок=True              : %d" % sum(1 for z in без if z.get("ок")))
пр = Counter()
for z in без[:4000]:
    b = z.get("брак")
    if b:
        пр[(b if isinstance(b, str) else json.dumps(b, ensure_ascii=False))[:70]] += 1
for k, v in пр.most_common(6):
    print("    %5d  %s" % (v, k))

print("\n=== ДЕНЬ (поле 'день', только строки с моделью) ===")
по_дн = {}
for z in с_моделью:
    д = str(z.get("день") or "нет")
    a = по_дн.setdefault(д, [0, 0, 0.0])
    a[0] += 1
    a[1] += 1 if z.get("ок") else 0
    a[2] += float(z.get("цена_$") or 0)
for д in sorted(по_дн, reverse=True)[:10]:
    n, k, c = по_дн[д]
    print("  %-12s обраб %4d | годных %4d (%3.0f%%) | $%7.2f | на годное $%.3f"
          % (д, n, k, 100.0 * k / max(1, n), c, c / max(1, k)))

print("\n=== ИТОГ ===")
свод("Meyer, генерация всего", с_моделью)
хв = с_моделью[-400:]
свод("Meyer, последние 400", хв)
