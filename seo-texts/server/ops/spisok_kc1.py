# -*- coding: utf-8 -*-
"""Список группы «КЦ-1» под генерацию (владелец 19.10: «КЦ-1 давай, пиши»).
Только направление КЦ (сегмент «кц» или target_division=kc), с ИНН. Порядок:
сначала адреса с вердиктом пробы «есть», потом непроверенные, потом «принимает
всё»/«неясно»; мёртвые — вон. Внутри — по выручке, крупные раньше.
Пишет _ops/spisok-kc1.json (id получателей). spisok_kc1.py [сколько первых]."""
import io
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
выр = {str(r[0]): float(r[1] or 0) for r in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub IS NOT NULL")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
ранг = {"есть": 0, "": 1, "принимает всё": 2, "неясно": 2}
ряды = []
from collections import Counter
сч = Counter()
for rid, em, inn, seg, ex in c.execute("SELECT id, email, inn, segment, extra_json FROM recipients WHERE extra_json LIKE '%КЦ-1%'"):
    x = json.loads(ex or "{}")
    if "КЦ-1" not in (x.get("gruppy") or []):
        continue
    if not (str(seg or "") == "кц" or x.get("target_division") == "kc"):
        сч["не КЦ по сегменту"] += 1
        continue
    if not inn:
        сч["без ИНН"] += 1
        continue
    в = проба.get(str(em).lower(), "")
    if в in ("нет ящика", "нет MX"):
        сч["мёртв по пробе (лесенка подменит в драйвере)"] += 1
    if в in ("неясно", "отказ пробе"):
        сч["вон: «%s» (владелец 20.10: такие с отправки снимаем)" % в] += 1
        continue
    сч["вердикт: " + (в or "не проверен")] += 1
    ряды.append((ранг.get(в, 1), -выр.get(str(inn), 0), rid))
ряды.sort()
import sys
if len(sys.argv) > 1:
    ряды = ряды[:int(sys.argv[1])]  # срез: отбор драйвера идёт ~0,15 с на компанию
json.dump([r[2] for r in ряды], io.open(r"C:\sender\_ops\spisok-kc1.json", "w"))
print("в списке:", len(ряды))
for k, v in сч.most_common():
    print("  ", k, v)
