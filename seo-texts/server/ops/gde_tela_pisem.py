# -*- coding: utf-8 -*-
"""Где на самом деле лежат тела: искал в «итоге», а они в «сгенерировано»."""
import io
import json
from collections import Counter


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
этапы = Counter()
с_телом = Counter()
тела = {}
брак_по_инн = {}
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines():
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        э = str(z.get("этап") or "(нет этапа)")
        этапы[э] += 1
        if z.get("тело"):
            с_телом[э] += 1
            и = цифры(z.get("inn"))
            if и:
                тела.setdefault(и, []).append(z)
        if (z.get("этап") == "итог" and not z.get("ок")
                and "нет представления первой строкой" in str(z.get("брак") or "")):
            брак_по_инн[цифры(z.get("inn"))] = z

print("=== СТРОКИ ЖУРНАЛА ПО ЭТАПАМ ===")
for э, n in этапы.most_common():
    print("   %-16s всего %6d, с телом %6d" % (э, n, с_телом.get(э, 0)))

брак_по_инн.pop("", None)
есть = [и for и in брак_по_инн if и in тела]
print("\n=== 142 СНЯТЫХ ЗА ПРЕДСТАВЛЕНИЕ ===")
print("   уникальных ИНН: %d" % len(брак_по_инн))
print("   у скольких тело в журнале ЕСТЬ: %d" % len(есть))
print("   у скольких тела нет вовсе:      %d" % (len(брак_по_инн) - len(есть)))

if есть:
    z = тела[есть[0]][-1]
    print("\n=== ПРИМЕР ТЕЛА (%s) ===" % z.get("имя"))
    print("   этап: %s, направление: %s, ок: %s"
          % (z.get("этап"), z.get("направление"), z.get("ок")))
    print("   тема: %s" % z.get("тема"))
    for стр in str(z.get("тело") or "").splitlines()[:12]:
        print("   | %s" % стр[:120])
    print("\n   есть ли «меня зовут»: %s"
          % ("да" if "меня зовут" in str(z.get("тело") or "").lower() else "НЕТ"))
