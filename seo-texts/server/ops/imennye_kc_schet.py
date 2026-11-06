# -*- coding: utf-8 -*-
"""Сколько компаний КЦ с ИМЕНОВАННЫМ контактом (contact_name) — по лучшей роли на компанию,
после исключений: ответ/отказ/жалоба, стоп-лист, мёртвый адрес, письмо любого направления < 21 дня."""
import collections, json, re, sqlite3
from datetime import datetime, timedelta
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
гр = (datetime.utcnow() - timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%S")
недавно = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent' AND ts>=? AND inn IS NOT NULL", (гр,))}
ответ = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
стоп = {v.lower() for s, v in c.execute("SELECT scope, value FROM suppression")}
проба = {e.lower(): v for e, v in c.execute("SELECT email, verdict FROM addr_probe")}
РОЛИ = [("тех", r"механик|энергетик|главн\w* инженер|техн\w* директор|начальник (цеха|производства)|технолог|ремонт|эксплуатац"),
        ("руководитель", r"директор|руководител|владел|учредител|генеральн"),
        ("снабжение", r"снабж|закуп|тендер"),
        ("hr/прочее", r".")]
def роль(ст):
    for н, rx in РОЛИ:
        if re.search(rx, ст or "", re.I): return н
    return "без должности"
лучший = {}
сч = collections.Counter()
for rid, em, inn, seg, имя, ex in c.execute("SELECT id, lower(email), inn, segment, contact_name, extra_json FROM recipients WHERE inn IS NOT NULL AND contact_name IS NOT NULL AND trim(contact_name)!=''"):
    x = json.loads(ex or "{}")
    кц = str(seg or "") == "кц" or x.get("target_division") == "kc" or "kc" in str(x.get("divisions") or "")
    if not кц: continue
    inn = str(inn)
    if inn in ответ: сч["искл: отвечали"] += 1; continue
    if em in стоп or inn in стоп: сч["искл: стоп-лист"] += 1; continue
    if проба.get(em) in ("нет ящика", "нет MX", "неясно", "отказ пробе"): сч["искл: адрес мёртв/неясно"] += 1; continue
    if inn in недавно: сч["искл: писали < 21 дня"] += 1; continue
    р = роль(x.get("stupen") or x.get("dolzhnost") or "")
    ранг = [н for н, _ in РОЛИ].index(р) if р in [н for н, _ in РОЛИ] else 9
    if inn not in лучший or ранг < лучший[inn][0]:
        лучший[inn] = (ранг, р)
print("исключено:", dict(сч))
print("компаний КЦ с именованным контактом (лучший на компанию):", len(лучший))
print("по роли лучшего:", collections.Counter(р for _, р in лучший.values()).most_common())
