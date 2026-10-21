# -*- coding: utf-8 -*-
"""Список группы «КЦ-1» под генерацию (владелец 19.10: «КЦ-1 давай, пиши»).
Только направление КЦ (сегмент «кц» или target_division=kc), с ИНН. Порядок:
сначала адреса с вердиктом пробы «есть», потом непроверенные, потом «принимает
всё»/«неясно»; мёртвые — вон. Внутри — по выручке, крупные раньше.
Пишет _ops/spisok-kc1.json (id получателей). spisok_kc1.py [сколько первых]."""
import io
import json
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
выр = {str(r[0]): float(r[1] or 0) for r in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub IS NOT NULL")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
ранг = {"есть": 0, "": 1, "принимает всё": 2, "неясно": 2}
ряды = []
from collections import Counter
# ПОВТОР КЦ <30 ДНЕЙ — ВОН ИЗ СПИСКА (владелец 21.10: «почему такие в генерацию
# попадают?»). Заслон панели (_povtor_razreshen) смотрит на extra.division
# получателя, а у компаний из «Россия 9000» там осталось «meyer» — прошлое письмо
# КЦ он считал «другим направлением» и пропускал. Здесь — по факту отправок:
# ИНН или адрес, которому письмо КЦ ушло меньше 30 дней назад, не берём.
from datetime import datetime, timedelta
_гр = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
_кц_камп = {r[0] for r in c.execute("SELECT id, name FROM campaigns") if r[0] in (1, 5, 6, 9, 10) or "КЦ" in str(r[1] or "")}
_недавно_инн, _недавно_адр = set(), set()
for _i, _e, _cid in c.execute("SELECT inn, lower(email), campaign_id FROM send_log WHERE outcome='sent' AND ts>=?", (_гр,)):
    if _cid in _кц_камп:
        if _i:
            _недавно_инн.add(str(_i))
        _недавно_адр.add(_e)
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
    if str(inn) in _недавно_инн or str(em).lower() in _недавно_адр:
        сч["письмо КЦ этой компании <30 дней (повтор)"] += 1
        continue
    в = проба.get(str(em).lower(), "")
    if в in ("нет ящика", "нет MX"):
        сч["мёртв по пробе (лесенка подменит в драйвере)"] += 1
    if в in ("неясно", "отказ пробе"):
        сч["вон: «%s» (владелец 20.10: такие с отправки снимаем)" % в] += 1
        continue
    сч["вердикт: " + (в or "не проверен")] += 1
    # ПРИОРИТЕТ (владелец 21.10, «вот тем, кто на скрине»): выручка от 100 млн
    # ИЛИ адрес — главный механик/энергетик, главный инженер, руководитель,
    # начальник производства. С ключом --prioritet в список идут только они.
    _в = выр.get(str(inn), 0) or float(x.get("revenue_rub") or 0) if str(x.get("revenue_rub") or "").replace(".", "").isdigit() else выр.get(str(inn), 0)
    _ст = str(x.get("stupen") or "").lower()
    _приор = _в >= 1e8 or any(s in _ст for s in ("механик", "энергетик", "главный инженер", "техдиректор", "руководитель", "начальник производства", "цеха"))
    if "--prioritet" in sys.argv and not _приор:
        сч["вне приоритета (--prioritet)"] += 1
        continue
    ряды.append((ранг.get(в, 1), -_в, rid))
ряды.sort()
_срез = [a for a in sys.argv[1:] if a.isdigit()]
if _срез:
    ряды = ряды[:int(_срез[0])]  # срез: отбор драйвера идёт ~0,15 с на компанию
json.dump([r[2] for r in ряды], io.open(r"C:\sender\_ops\spisok-kc1.json", "w"))
print("в списке:", len(ряды))
for k, v in сч.most_common():
    print("  ", k, v)
