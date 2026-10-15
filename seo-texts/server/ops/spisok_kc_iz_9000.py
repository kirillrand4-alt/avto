# -*- coding: utf-8 -*-
"""Список recipient_id для генерации КЦ (владелец 15.10): компании группы
«Россия 9000» с паспортом сайта, которые не подошли Meyer (вердикт «кц» /
«не мейер» либо брак Meyer по линзе), и которым ещё ни одного письма не
ставили. Пишет C:\\sender\\_ops\\spisok-kc-iz-9000.json, печатает разбивку."""
import glob
import io
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
паспорт = {str(r[0]) for r in e.execute(
    "SELECT inn FROM site_facts WHERE facts_json IS NOT NULL AND length(facts_json) > 20")}
напр = {str(r[0]): (r[1] or "") for r in e.execute("SELECT inn, verdikt_napr FROM companies")}
с_письмом = {str(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE r.inn IS NOT NULL")}
брак_мейер = set()
for ф in glob.glob(r"C:\sender\_ops\gen-*.jsonl"):
    for стр in io.open(ф, encoding="utf-8", errors="replace"):
        if '"итог"' not in стр:
            continue
        try:
            з = json.loads(стр)
        except ValueError:
            continue
        if not з.get("ок") and str(з.get("направление") or "") == "meyer":
            брак_мейер.add(str(з.get("inn") or ""))
сч, рид, видели = Counter(), [], set()
for rid, inn, ex in c.execute("SELECT id, inn, extra_json FROM recipients WHERE inn IS NOT NULL ORDER BY id"):
    inn = str(inn)
    if "Россия 9000" not in str(ex or "") or inn in видели:
        continue
    видели.add(inn)
    сч["в группе"] += 1
    if inn not in паспорт:
        сч["нет паспорта"] += 1; continue
    н = напр.get(inn, "")
    if н != "кц":
        сч["Meyer подходит/без вердикта: %s" % (н or "-")] += 1; continue
    if н in ("никуда", "не кц"):
        сч["не подходит никому"] += 1; continue
    if inn in с_письмом:
        сч["письмо уже было"] += 1; continue
    рид.append(rid)
сч["К ГЕНЕРАЦИИ"] = len(рид)
json.dump(рид, io.open(r"C:\sender\_ops\spisok-kc-iz-9000.json", "w"))
for k, v in сч.most_common():
    print("%6d  %s" % (v, k))
