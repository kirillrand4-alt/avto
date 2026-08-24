# -*- coding: utf-8 -*-
"""Сохраняется ли текст забракованного письма под ключом «тело_брака».

Первый замер искал ключ «тело» и не нашёл ничего. Но в partiya_gen есть
ветка elif черновик: зап["тело_брака"] = черновик.get("body") — то есть
текст брака кладётся под ДРУГИМ ключом. Проверяем по журналу.
"""
import io
import json
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
записи = []
for с in io.open(ЖУРНАЛ, encoding="utf-8"):
    с = с.strip()
    if с:
        try:
            записи.append(json.loads(с))
        except Exception:  # noqa: BLE001
            pass

ключи = Counter()
for з in записи:
    for к in з:
        if "тело" in к or "тема" in к:
            ключи[к] += 1
print("ключи с текстом в журнале: %s" % dict(ключи))


def по_заходу(з):
    п = з.get("брак") or []
    п = п if isinstance(п, list) else [str(п)]
    return any("израсходован" in str(x).lower() or "анти-штамп" in str(x).lower()
               for x in п)


брак = [з for з in записи if з.get("ок") is False]
заход = [з for з in брак if по_заходу(з)]
с_черновиком = [з for з in заход if з.get("тело_брака")]
print("\nбрак всего: %d, по заходу: %d" % (len(брак), len(заход)))
print("из них С ЧЕРНОВИКОМ (тело_брака непусто): %d" % len(с_черновиком))

# уникальные компании, у которых ещё нет годного письма
готовые = {str(з.get("inn")) for з in записи if з.get("ок") or з.get("тело")}
спасаемые = {}
for з in с_черновиком:
    inn = str(з.get("inn"))
    if inn in готовые:
        continue
    # берём последний черновик компании
    спасаемые[inn] = з
print("из них у компаний БЕЗ годного письма: %d уникальных ИНН" % len(спасаемые))

попыток = Counter()
for з in записи:
    if з.get("inn") and з.get("этап") != "итог":
        попыток[str(з.get("inn"))] += 1
исчерпаны = sum(1 for i in спасаемые if попыток[i] >= 3)
print("  из них исчерпали 3 попытки (иначе выбыли навсегда): %d" % исчерпаны)
print("  ещё в пуле: %d" % (len(спасаемые) - исчерпаны))

print("\n=== ПРИМЕРЫ ЧЕРНОВИКОВ ===")
for inn, з in list(спасаемые.items())[:3]:
    print("\n  %s (ИНН %s), попыток %d" % (str(з.get("имя"))[:44], inn,
                                           попыток[inn]))
    print("    брак: %s" % "; ".join(str(x)[:100] for x in (з.get("брак") or [])))
    print("    тема: %s" % str(з.get("тема_брака"))[:70])
    т = str(з.get("тело_брака") or "")
    print("    первый абзац: %s" % т.split("\n\n")[0][:180].replace("\n", " "))
    print("    длина тела: %d знаков" % len(т))
