# -*- coding: utf-8 -*-
"""У 1424 фирм брака в журнале нет — на что тогда ушли их три попытки."""
import io
import json
from collections import Counter, defaultdict


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
попыток, готово = Counter(), set()
этапы_фирмы = defaultdict(Counter)
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines():
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        и = цифры(z.get("inn"))
        if not и:
            continue
        э = str(z.get("этап") or "(нет)")
        if э == "отмена_попытки":
            попыток[и] = max(0, попыток[и] - 1)
            continue
        if z.get("ок") or z.get("тело"):
            готово.add(и)
        if э != "итог":
            попыток[и] += 1
        этапы_фирмы[и][э] += 1

выбыли = [и for и in попыток if попыток[и] >= 3 and и not in готово]
без_брака = [и for и in выбыли if not этапы_фирмы[и].get("итог")]
print("выбывших: %d, из них без единого «итога»: %d"
      % (len(выбыли), len(без_брака)))

свод = Counter()
for и in без_брака:
    for э, n in этапы_фирмы[и].items():
        свод[э] += n
print("\n=== ИЗ ЧЕГО СОСТОЯЛИ ИХ ПОПЫТКИ ===")
for э, n in свод.most_common():
    print("   %-18s %6d записей" % (э, n))

# что писал предклассификатор про них
пример = Counter()
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines():
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        if str(z.get("этап")) != "предкласс_отсев":
            continue
        if цифры(z.get("inn")) in set(без_брака):
            пример[str(z.get("вердикт") or z.get("причина")
                       or z.get("напр_почему") or "(без пометки)")[:60]] += 1
print("\n=== ВЕРДИКТЫ ПРЕДКЛАССИФИКАТОРА ПО НИМ ===")
for в, n in пример.most_common(8):
    print("   %5d  %s" % (n, в))
print("\n=== ИТОГ ===")
print("если попытки состоят из предкласс_отсев — компанию не писали ни разу,")
print("её трижды признали «никуда» дешёвой моделью по паспорту сайта.")
