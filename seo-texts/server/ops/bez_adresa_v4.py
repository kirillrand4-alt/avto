# -*- coding: utf-8 -*-
"""Компании ФСА v4 (ярусы A/B), которые не залились «без годного адреса»
(владелец 23.10: «а других адресов не было? правильно ли уехали адреса?»).
По каждой: все кандидаты (лучший из файла, контакты сайта, наши enrich.emails)
и почему отпал: чей это адрес в панели (ИНН, название, группы, писали ли),
стоп-лист, проба. Сводка по причинам + примеры. Только чтение."""
import json
import os
import sqlite3
from collections import Counter

import requests

У = os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/")
H = {"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}
c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
стоп = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
получ = {}
for em, inn, имя, ex in c.execute("SELECT lower(email), inn, company_name, extra_json FROM recipients"):
    получ[em] = (str(inn or ""), str(имя or "")[:40], ",".join((json.loads(ex or "{}").get("gruppy") or [])[:2]))
писали = {str(r[0]).lower() for r in c.execute("SELECT DISTINCT email FROM send_log WHERE outcome='sent'")}
мои = {str(r[0]) for r in c.execute("SELECT inn FROM recipients WHERE extra_json LIKE '%v4-%'")}
import re
import sys
sys.path.insert(0, r"C:\sender\server")
try:
    from lead_scoring import _rol_ball
except Exception:  # noqa: BLE001
    def _rol_ball(_р):
        return 4
ПЛОХО = re.compile(r"(?i)кадр|бухгалт|финанс|hr|резюме|не для письма")
ПУБ = ("mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru", "gmail.com", "rambler.ru")
сч, тип, примеры = Counter(), Counter(), []
for ф in ("volna2-zaliv.json", "volna2-zaliv-b.json"):
    д = requests.get(У + "/" + ф, headers=H, timeout=120).json()
    конт = {}
    for к in д["cont"]:
        конт.setdefault(к["inn"], []).append(к["email"])
    for к in д["comp"]:
        inn = к["inn"]
        if inn in мои:
            continue
        сч["компаний без адреса"] += 1
        канд = [к["best"]] + конт.get(inn, []) + [r[0] for r in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (inn,))
                                                   if not ПЛОХО.search(str(r[1] or "")) and _rol_ball(str(r[1] or "")) > 1]
        канд = list(dict.fromkeys(a for a in канд if a and "@" in a and not ПЛОХО.search(a.split("@")[0])))
        if any(a not in получ and a not in стоп and a.split("@")[-1] not in стоп and проба.get(a) not in ("нет ящика", "нет MX")
               for a in канд):
            сч["есть свободный годный адрес (не взят при заливке)"] += 1
        сч["кандидатов всего"] += len(канд)
        if len(канд) == 1:
            сч["только 1 адрес на компанию"] += 1
        for a in канд:
            if a in стоп or a.split("@")[-1] in стоп:
                тип["стоп-лист"] += 1
            elif проба.get(a) in ("нет ящика", "нет MX"):
                тип["мёртв по пробе"] += 1
            elif a in получ:
                чужой_инн, имя, гр = получ[a]
                дом = a.split("@")[-1]
                вид = "публичный ящик" if дом in ПУБ else "корпоративный домен"
                тип["в панели под другим ИНН — %s%s" % (вид, ", ему уже писали" if a in писали else "")] += 1
                if len(примеры) < 14:
                    примеры.append("%s | %s | адрес %s → в панели ИНН %s «%s» (%s)%s" % (
                        inn, к["name"][:35], a, чужой_инн, имя, гр, " писали" if a in писали else ""))
            else:
                тип["?? годный, но не взят"] += 1
print(dict(сч))
for k, v in тип.most_common():
    print("  %5d  %s" % (v, k))
print("\nпримеры:")
for p in примеры:
    print("  ", p)

# ЛЕСЕНКА ДЛЯ СНЯТЫХ ПРОБОЙ (владелец 23.10: «а следующие в лесенке есть
# контакты?»): получатели v4-A/B с вердиктом неясно/отказ/мёртв — есть ли у
# компании другой адрес: не в панели, не мёртвый, роль годная.
лс = Counter()
пр2 = []
for rid, em, inn in c.execute("SELECT id, lower(email), inn FROM recipients WHERE extra_json LIKE '%v4-%'").fetchall():
    в = проба.get(em, "")
    if в not in ("неясно", "отказ пробе", "нет ящика", "нет MX"):
        continue
    лс["снято пробой"] += 1
    if c.execute("SELECT 1 FROM messages WHERE recipient_id=?", (rid,)).fetchone():
        continue
    запас = []
    for a, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (str(inn),)):
        if a == em or a in стоп or a.split("@")[-1] in стоп or ПЛОХО.search(str(роль or "") + a.split("@")[0]):
            continue
        if проба.get(a) in ("нет ящика", "нет MX", "неясно", "отказ пробе"):
            continue
        if a in получ and получ[a][0] != str(inn):
            continue
        запас.append((проба.get(a) or "не проверен", a, str(роль or "")[:25]))
    if запас:
        лс["есть следующий по лесенке"] += 1
        лс["  из них проверен «есть»/«принимает всё»"] += any(x[0] in ("есть", "принимает всё") for x in запас)
        if len(пр2) < 8:
            пр2.append((inn, em, в, запас[:3]))
    else:
        лс["запасного нет"] += 1
print("\nЛЕСЕНКА для снятых пробой:", dict(лс))
for p in пр2:
    print("  ", p)
