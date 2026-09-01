# -*- coding: utf-8 -*-
"""Считает ли резюм эти компании отработанными.

partiya_gen помечает фирму сделанной, если в журнале есть «ок» ИЛИ «тело».
У сорвавшихся генераций нет ни того, ни другого — значит следующий прогон
возьмёт их снова. Проверяем это, а не верим на слово.
"""
import io
import json
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
сделано = set()
попыток = Counter()
сорвались = []
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    строки = f.readlines()
for с in строки:
    try:
        z = json.loads(с)
    except Exception:                                         # noqa: BLE001
        continue
    инн = str(z.get("inn") or "")
    if not инн:
        continue
    if z.get("этап") == "отмена_попытки":
        попыток[инн] = max(0, попыток[инн] - 1)
        continue
    if z.get("этап") != "итог":
        попыток[инн] += 1
    if z.get("ок") or z.get("тело"):
        сделано.add(инн)

for с in строки[-9000:]:
    try:
        z = json.loads(с)
    except Exception:                                         # noqa: BLE001
        continue
    if (z.get("этап") == "итог" and not z.get("ок")
            and "нет представления первой строкой" in str(z.get("брак") or "")):
        сорвались.append(str(z.get("inn") or ""))

сорвались = [и for и in сорвались if и]
вернутся = [и for и in сорвались if и not in сделано]
исчерпали = [и for и in вернутся if попыток[и] >= 3]
print("=== СОРВАВШИЕСЯ ГЕНЕРАЦИИ ===")
print("   всего таких записей: %d, уникальных ИНН: %d"
      % (len(сорвались), len(set(сорвались))))
print("   помечены отработанными (тело есть): %d"
      % len([и for и in сорвались if и in сделано]))
print("   ВЕРНУТСЯ в пул следующим прогоном: %d" % len(set(вернутся)))
print("   из них исчерпали лимит в 3 попытки: %d" % len(set(исчерпали)))
print("\n   распределение попыток у вернувшихся:")
for n, ск in Counter(попыток[и] for и in set(вернутся)).most_common():
    print("      %d попыток — %d фирм" % (n, ск))
print("\n=== ИТОГ ===")
print("чинить руками нечего: тел нет. Компании сами вернутся в отбор,")
print("кроме тех, кто выбрал три попытки.")
