# -*- coding: utf-8 -*-
"""1945 фирм, выбывших по лимиту попыток: чем они занимаются и за что брак."""
import io
import json
import sqlite3
from collections import Counter, defaultdict


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
попыток, готово = Counter(), set()
брак = defaultdict(list)
имена, напр = {}, {}
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines():
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        и = цифры(z.get("inn"))
        if not и:
            continue
        э = str(z.get("этап") or "")
        if э == "отмена_попытки":
            попыток[и] = max(0, попыток[и] - 1)
            continue
        if z.get("ок") or z.get("тело"):
            готово.add(и)
        if э != "итог":
            попыток[и] += 1
        if z.get("имя"):
            имена[и] = z["имя"]
        if z.get("направление"):
            напр[и] = z["направление"]
        if э == "итог" and not z.get("ок") and z.get("брак"):
            брак[и].append(str(z["брак"])[:160])

выбыли = sorted(и for и in попыток if попыток[и] >= 3 and и not in готово)
print("выбывших фирм: %d" % len(выбыли))

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row
карточки = {}
for i in range(0, len(выбыли), 400):
    ч = выбыли[i:i + 400]
    for r in e.execute("SELECT inn, name, okved, activity, site, division,"
                       "       revenue_rub FROM companies WHERE inn IN (%s)"
                       % ",".join("?" * len(ч)), ч):
        карточки[цифры(r["inn"])] = dict(r)
паспорта = {}
for i in range(0, len(выбыли), 400):
    ч = выбыли[i:i + 400]
    for r in e.execute("SELECT inn, facts_json FROM site_facts WHERE inn IN (%s)"
                       % ",".join("?" * len(ч)), ч):
        try:
            d = json.loads(r["facts_json"] or "{}") or {}
        except Exception:                                     # noqa: BLE001
            d = {}
        прод = d.get("продукция") or []
        if isinstance(прод, str):
            прод = [прод]
        паспорта[цифры(r["inn"])] = "; ".join(str(x) for x in прод[:3])
e.close()

print("\n=== ОТКУДА ОНИ ===")
print("   есть карточка в обогащении: %d" % len(карточки))
print("   есть паспорт сайта:         %d" % len(паспорта))
print("   направление в прогоне: %s"
      % dict(Counter(напр.get(и, "?") for и in выбыли).most_common(4)))
коды = Counter()
for и in выбыли:
    к = str((карточки.get(и) or {}).get("okved") or "")
    коды[к.split(".")[0] if к else "нет"] += 1
print("\n=== ОКВЭД (раздел) ===")
for к, n in коды.most_common(12):
    print("   %-6s %5d" % (к, n))

вид = Counter()
for и in выбыли:
    т = " ".join(брак.get(и) or []).lower()
    if "не покупатель" in т:
        вид["линза: не покупатель"] += 1
    elif "нет json" in т or "прогон упал" in т:
        вид["прогон сорвался / нет JSON"] += 1
    elif "объ" in т and "слов" in т:
        вид["объём вне нормы"] += 1
    elif "отказ" in т or "отправлять нельзя" in т:
        вид["модель отказалась писать"] += 1
    elif т:
        вид["прочий редакторский брак"] += 1
    else:
        вид["брака в журнале нет"] += 1
print("\n=== ЗА ЧТО ВЫБЫЛИ ===")
for в, n in вид.most_common():
    print("   %-30s %5d" % (в, n))

print("\n=== ДВАДЦАТЬ ГЛАЗАМИ ===")
показано = 0
for и in выбыли:
    к = карточки.get(и)
    if not к:
        continue
    показано += 1
    print("\n   %s · ИНН %s · ОКВЭД %s · %s"
          % (str(к.get("name"))[:52], и, к.get("okved"), к.get("division")))
    if к.get("activity"):
        print("      род занятий: %s" % str(к["activity"])[:100])
    if паспорта.get(и):
        print("      с сайта:     %s" % паспорта[и][:100])
    if брак.get(и):
        print("      брак:        %s" % брак[и][-1][:110])
    if показано >= 20:
        break
