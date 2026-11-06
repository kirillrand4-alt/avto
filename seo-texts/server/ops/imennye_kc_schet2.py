# -*- coding: utf-8 -*-
"""Компании КЦ (obzvon.division содержит kc) с контактом из enrich.imena (mozhno_po_imeni) —
лучший по роли на компанию, после исключений (ответ/отказ/жалоба, стоп-лист, мёртвый адрес,
письмо любого направления < 21 дня)."""
import collections, re, sqlite3
from datetime import datetime, timedelta
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
o = sqlite3.connect("file:C:\\sender\\obzvon-index.db?mode=ro", uri=True, timeout=30)
print("imena колонки mozhno_po_imeni:", e.execute("SELECT mozhno_po_imeni, COUNT(*) FROM imena GROUP BY 1").fetchall())
кц = {str(i) for i, d in o.execute("SELECT inn, division FROM obzvon") if "kc" in str(d or "").lower() or "кц" in str(d or "").lower()}
print("компаний КЦ в базе обзвона:", len(кц))
гр = (datetime.utcnow() - timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%S")
недавно = {str(r[0]) for r in s.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent' AND ts>=? AND inn IS NOT NULL", (гр,))}
ответ = {str(r[0]) for r in s.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
стоп = {v.lower() for _, v in s.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in s.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX','неясно','отказ пробе')")}
писали_когда_то = {str(r[0]) for r in s.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent' AND inn IS NOT NULL")}
РОЛИ = [("тех", r"механик|энергетик|главн\w* инженер|техн\w* директор|начальник (цеха|производства)|технолог|ремонт|эксплуатац"),
        ("руководитель", r"директор|руководител|владел|учредител|генеральн|президент"),
        ("снабжение", r"снабж|закуп|тендер"), ("hr/прочее", r".")]
лучший = {}; сч = collections.Counter()
print("emails.imya_ok:", e.execute("SELECT imya_ok, COUNT(*) FROM emails WHERE person IS NOT NULL AND trim(person)!='' GROUP BY 1").fetchall())
for inn, person, post, role, em, мож in e.execute("SELECT inn, person, COALESCE(zahod_rol,''), role, email, imya_ok FROM emails WHERE person IS NOT NULL AND trim(person)!='' AND email IS NOT NULL"):
    inn = str(inn); em = (em or "").lower()
    if inn not in кц: continue
    if str(мож) not in ("1", "True", "true", "да"): сч["нельзя по имени"] += 1; continue
    if inn in ответ: сч["искл: отвечали"] += 1; continue
    if em in стоп or inn in стоп: сч["искл: стоп-лист"] += 1; continue
    if em in мёртв: сч["искл: адрес мёртв/неясно"] += 1; continue
    if inn in недавно: сч["искл: писали < 21 дня"] += 1; continue
    т = (post or "") + " " + (role or "")
    р = next(н for н, rx in РОЛИ if re.search(rx, т, re.I)) if т.strip() else "без должности"
    ранг = ["тех", "руководитель", "снабжение", "hr/прочее", "без должности"].index(р)
    if inn not in лучший or ранг < лучший[inn][0]:
        лучший[inn] = (ранг, р)
print("исключено (строк):", dict(сч))
print("компаний с именем (лучший контакт):", len(лучший), "| из них писали когда-либо:", sum(1 for i in лучший if i in писали_когда_то))
print("по роли:", collections.Counter(р for _, р in лучший.values()).most_common())
