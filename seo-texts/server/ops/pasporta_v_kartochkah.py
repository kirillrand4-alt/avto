# -*- coding: utf-8 -*-
"""Доехали ли паспорта до карточек и как это сказалось на браке.

Утром замер показал: site_facts лежит в обогащении, а в recipients.extra_json
его нет ни у одного письма. Владелец говорит, что загрузили новые паспорта —
проверяем, видно ли это в карточках и меняется ли отдача.
"""
import io
import json
import os
import sqlite3
import time
from collections import Counter, defaultdict

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
последние = []
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    строки = f.readlines()
for с in строки[-4000:]:
    try:
        последние.append(json.loads(с))
    except Exception:                                         # noqa: BLE001
        pass
print("ключи строки журнала: %s" % sorted(последние[-1].keys()))
print("последняя строка: %s" % json.dumps(
    {к: (str(v)[:40] if not isinstance(v, (int, float)) else v)
     for к, v in последние[-1].items()}, ensure_ascii=False)[:300])

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row

print("\n=== ПАСПОРТ САЙТА В КАРТОЧКАХ ГРУППЫ, ПО ДАТЕ ЗАВЕДЕНИЯ ===")
итоги = defaultdict(lambda: [0, 0])
for r in c.execute("SELECT substr(created_at,1,10) д, extra_json FROM recipients"
                   " WHERE COALESCE(extra_json,'') LIKE '%Партия 935%'"):
    д = r["д"]
    итоги[д][0] += 1
    try:
        доп = json.loads(r["extra_json"] or "{}") or {}
    except Exception:                                         # noqa: BLE001
        доп = {}
    if доп.get("site_facts"):
        итоги[д][1] += 1
for д in sorted(итоги, reverse=True)[:10]:
    всего, с_пасп = итоги[д]
    print("   %s  карточек %6d, с паспортом %6d (%.0f%%)"
          % (д, всего, с_пасп, 100.0 * с_пасп / всего if всего else 0))

print("\n=== ЭТОТ ПРОГОН: ОТДАЧА ПО ВОЗРАСТУ КАРТОЧКИ ===")
# берём все строки очереди этого прогона + брак из журнала по времени
свежие_инн = set()
for r in c.execute("SELECT inn, substr(created_at,1,10) д FROM recipients"
                   " WHERE inn IS NOT NULL"
                   "   AND COALESCE(extra_json,'') LIKE '%Партия 935%'"):
    if r["д"] >= "2026-08-31":
        свежие_инн.add(str(r["inn"] or ""))

порог = time.time() - 4 * 3600
поле_времени = None
for к in ("ts", "время", "time", "when"):
    if к in последние[-1]:
        поле_времени = к
        break
свои = []
for z in последние:
    т = z.get(поле_времени) if поле_времени else None
    if isinstance(т, (int, float)) and т >= порог:
        свои.append(z)
    elif isinstance(т, str) and т >= time.strftime(
            "%Y-%m-%dT%H:%M", time.localtime(порог)):
        свои.append(z)
print("   строк журнала за 4 часа: %d (поле времени: %s)"
      % (len(свои), поле_времени))

сч = defaultdict(Counter)
for z in свои:
    if z.get("этап") != "итог":
        continue
    и = str(z.get("inn") or "")
    группа = "заведены 31.08" if и in свежие_инн else "заведены раньше"
    сч[группа]["ок" if z.get("ок") else "брак"] += 1
for г in sorted(сч):
    всего = sum(сч[г].values())
    print("   %-18s всего %4d, ок %4d (%.0f%%), брак %4d"
          % (г, всего, сч[г]["ок"], 100.0 * сч[г]["ок"] / всего, сч[г]["брак"]))

брак_причины = Counter()
for z in свои:
    if z.get("этап") == "итог" and not z.get("ок"):
        брак_причины[str(z.get("причина") or z.get("brak") or "")[:70]] += 1
if брак_причины:
    print("\n   причины брака:")
    for п, n in брак_причины.most_common(6):
        print("      %-70s %3d" % (п or "(не записана)", n))
c.close()

print("\n=== ИТОГ ===")
всего_гр = sum(v[0] for v in итоги.values())
с_пасп_гр = sum(v[1] for v in итоги.values())
print("в группе «Партия 935» карточек %d, из них с паспортом сайта %d (%.0f%%)"
      % (всего_гр, с_пасп_гр, 100.0 * с_пасп_гр / всего_гр if всего_гр else 0))
