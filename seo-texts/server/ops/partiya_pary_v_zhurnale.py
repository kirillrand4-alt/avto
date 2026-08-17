# -*- coding: utf-8 -*-
"""Идут ли записи журнала парами и есть ли в них тело письма.

Живая проверка правки «текст письма на диск ДО первого обращения к базе».
Признак того, что она работает: на письмо в gen-partiya-935.jsonl две
строки - первая с темой и телом, вторая («итог») с review_id.

Имя первого этапа бывает двух видов: «текст» и «сгенерировано» (правку
писали две сессии одновременно, 17.08). Принимаем оба - см. НАЧАЛО.

Ничего не пишет, база открывается на чтение.
"""
import io
import json
import os
import sqlite3
import time
from collections import Counter, OrderedDict

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
НАЧАЛО = ("текст", "сгенерировано")

сырые = []
for s in io.open(Ж, encoding="utf-8"):
    s = s.strip()
    if not s:
        continue
    try:
        сырые.append(json.loads(s))
    except Exception:                                          # noqa: BLE001
        pass

стар = [z for z in сырые if not z.get("этап")]
нов = [z for z in сырые if z.get("этап")]
этапы = Counter(z["этап"] for z in нов)

# схлопываем пары ровно как partiya_hod.py
пары, попытка = OrderedDict(), {}
for i, x in enumerate(сырые):
    rid, этап = x.get("recipient_id"), x.get("этап")
    if этап in НАЧАЛО:
        попытка[rid] = попытка.get(rid, 0) + 1
        пары[(rid, попытка[rid])] = x
    elif этап == "итог":
        пары[(rid, попытка.get(rid, 1))] = x
    else:
        пары[("стар", i)] = x

print(f"сырых строк в журнале: {len(сырые)}")
print(f"  старых (без этапа):  {len(стар)}")
print(f"  новых (с этапом):    {len(нов)}  {dict(этапы)}")
print(f"после схлопывания пар: {len(пары)}  "
      f"(строк схлопнуто: {len(сырые) - len(пары)})")
print(f"писем с телом среди новых: "
      f"{sum(1 for z in нов if z.get('этап') in НАЧАЛО and z.get('тело'))}")

# --- пары как они есть ---------------------------------------------------
группы = OrderedDict()
для_счёта = {}
for z in нов:
    rid = z.get("recipient_id")
    if z.get("этап") in НАЧАЛО:
        для_счёта[rid] = для_счёта.get(rid, 0) + 1
    ключ = (rid, для_счёта.get(rid, 1))
    группы.setdefault(ключ, []).append(z)

print(f"\nновых писем (пар): {len(группы)}")
print(f"{'rid':<7}{'строк':<7}{'этапы':<26}{'тело':<9}{'тема':<7}"
      f"{'review_id':<11}{'ок':<5}имя")
целых = битых = 0
for (rid, n), стр in группы.items():
    эт = "+".join(z.get("этап", "?") for z in стр)
    тело = max((len(z.get("тело") or "") for z in стр), default=0)
    тема = any(z.get("тема") for z in стр)
    rev = next((z.get("review_id") for z in стр if z.get("review_id")), None)
    ок = стр[-1].get("ок")
    имя = str(стр[-1].get("имя"))[:26]
    парой = len(стр) == 2 and стр[0].get("этап") in НАЧАЛО \
        and стр[-1].get("этап") == "итог"
    целых += 1 if парой else 0
    битых += 0 if парой else 1
    print(f"{rid:<7}{len(стр):<7}{эт:<26}{тело or '-':<9}"
          f"{'да' if тема else '-':<7}{str(rev or '-'):<11}"
          f"{'да' if ок else 'нет':<5}{имя}")

print(f"\nцелых пар «начало»+«итог»: {целых} | не пар: {битых}")

# --- панель --------------------------------------------------------------
conn = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True, timeout=30)
conn.row_factory = sqlite3.Row
ревы = {z.get("review_id") for z in нов if z.get("review_id")}
есть = 0
for rev in sorted(ревы):
    r = conn.execute("SELECT id, campaign_id, status, length(body) AS n "
                     "FROM confirm_reviews WHERE id=?", (int(rev),)).fetchone()
    if r:
        есть += 1
        print(f"  карточка #{r['id']}: кампания {r['campaign_id']}, "
              f"{r['status']}, тело {r['n']} знаков")
print(f"\nreview_id из новых записей: {len(ревы)}, "
      f"из них есть карточка в панели: {есть}")
for cid in (10, 11):
    ст = Counter(x["status"] for x in conn.execute(
        "SELECT status FROM confirm_reviews WHERE campaign_id=?", (cid,)))
    print(f"кампания {cid}: всего {sum(ст.values())} {dict(ст)}")
print("журнал изменён:", time.strftime(
    "%H:%M:%S", time.localtime(os.path.getmtime(Ж))),
    "| сейчас:", time.strftime("%H:%M:%S"))
