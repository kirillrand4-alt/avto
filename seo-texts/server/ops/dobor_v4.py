# -*- coding: utf-8 -*-
"""Добор ФСА v4 Meyer (владелец 23.10: «да, делай»):
  1) компании ярусов A/B без получателя, у которых есть СВОБОДНЫЙ годный адрес
     (не в панели, не в стоп-листе, не мёртв/неясно/отказ, роль не кадры/
     бухгалтерия, у обогащения роль > 1) — заводим получателя, как zalit_volna2;
  2) получатели v4-A/B, снятые пробой (неясно/отказ/мёртв) и без письма, —
     ставим следующий контакт по лесенке (сперва «есть», потом «принимает
     всё», потом непроверенный), адрес не должен числиться за другим ИНН.
Список id — _ops/spisok-v4-dobor.json. Журнал _ops/dobor-v4.jsonl (откат
адресов: --otkat). Без --primenit — счёт.
    dobor_v4.py [--primenit | --otkat]"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

import requests

sys.path.insert(0, r"C:\sender\server")
try:
    from lead_scoring import _rol_ball
except Exception:  # noqa: BLE001
    def _rol_ball(_р):
        return 4

ЖУР = r"C:\sender\_ops\dobor-v4.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in reversed(з):
            if x["что"] == "адрес":
                c.execute("UPDATE recipients SET email=?, domain=? WHERE id=?", (x["bylo"], x["bylo"].split("@")[-1], x["id"]))
            elif x["что"] == "новый":
                c.execute("DELETE FROM recipients WHERE id=? AND NOT EXISTS (SELECT 1 FROM messages WHERE recipient_id=?)",
                          (x["id"], x["id"]))
    print("откат:", len(з))
    sys.exit()
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=120)
У = os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/")
H = {"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}
ПЛОХО = re.compile(r"(?i)кадр|бухгалт|финанс|hr|резюме|не для письма")
ПЛОХИЕ_ВЕРДИКТЫ = ("нет ящика", "нет MX", "неясно", "отказ пробе")
РАНГ = {"есть": 0, "принимает всё": 1, "": 2}
стоп = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
получ = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, inn FROM recipients")}
инн_в_панели = set(получ.values())
т = time.strftime("%Y-%m-%dT%H:%M:%S")
сч = Counter()


def годен(а, роль, inn):
    if not а or "@" not in а or а in стоп or а.split("@")[-1] in стоп:
        return False
    if ПЛОХО.search(str(роль or "")) or ПЛОХО.search(а.split("@")[0]):
        return False
    if проба.get(а) in ПЛОХИЕ_ВЕРДИКТЫ:
        return False
    return а not in получ or получ[а] == inn


def лучший(кандидаты):
    return sorted(кандидаты, key=lambda к: (РАНГ.get(проба.get(к[0], ""), 2), к[2]))


новые, смена, ids = [], [], []
# 1) компании без получателя
for ф, ярус in (("volna2-zaliv.json", "A"), ("volna2-zaliv-b.json", "B")):
    д = requests.get(У + "/" + ф, headers=H, timeout=120).json()
    конт = {}
    for к in д["cont"]:
        конт.setdefault(к["inn"], []).append(к)
    for к in д["comp"]:
        inn = к["inn"]
        if inn in инн_в_панели:
            continue
        канд = []
        if годен(к["best"], "", inn):
            канд.append((к["best"], к.get("best_dolzh") or "лучший контакт файла", 0))
        for x in конт.get(inn, []):
            if str(x.get("step") or "").lower() != "никогда" and годен(x["email"], x.get("role"), inn):
                канд.append((x["email"], x.get("dolzh") or x.get("role"), 1))
        for а, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (inn,)):
            if годен(а, роль, inn) and _rol_ball(str(роль or "")) > 1:
                канд.append((а, роль, 2))
        if not канд:
            continue
        а, роль, _ = лучший(канд)[0]
        получ[а] = inn
        инн_в_панели.add(inn)
        extra = {"gruppy": ["ФСА волна 1"], "istochnik": "FSA-MEYER-v4-Meyer.xlsx", "volna": "v4-" + ярус,
                 "target_division": "meyer", "target_division_istochnik": "ФСА v4 добор, владелец 23.10",
                 "dolzhnost": роль, "site": к.get("site"), "revenue_rub": к.get("rev"),
                 "pochemu_meyer": к.get("pochemu"), "pasport_fsa": к.get("pasport")}
        новые.append((а, а.split("@")[-1], inn, к["name"], к["okved"], "meyer", None, "fsa-v4", к.get("region"),
                      "Europe/Moscow", json.dumps({k: v for k, v in extra.items() if v}, ensure_ascii=False), т, т))
        сч["1) новый получатель (свободный адрес)"] += 1
# 2) лесенка для снятых пробой
for rid, em, inn in c.execute("SELECT id, lower(email), inn FROM recipients WHERE extra_json LIKE '%v4-%'").fetchall():
    if проба.get(em) not in ПЛОХИЕ_ВЕРДИКТЫ or c.execute("SELECT 1 FROM messages WHERE recipient_id=?", (rid,)).fetchone():
        continue
    inn = str(inn)
    канд = [(а, роль, -_rol_ball(str(роль or ""))) for а, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (inn,))
            if а != em and годен(а, роль, inn) and а not in получ]
    if not канд:
        сч["2) запасного нет"] += 1
        continue
    а = лучший(канд)[0][0]
    получ[а] = inn
    смена.append((rid, em, а))
    сч["2) адрес заменён следующим по лесенке (%s)" % (проба.get(а) or "не проверен")] += 1
print(dict(сч))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for r in новые:
        cur = c.execute("INSERT OR IGNORE INTO recipients (email, domain, inn, company_name, okved, segment, contact_name, source, region,"
                        " tz, extra_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", r)
        if cur.rowcount:
            ids.append(cur.lastrowid)
            ж.write(json.dumps({"что": "новый", "id": cur.lastrowid, "email": r[0], "inn": r[2]}, ensure_ascii=False) + "\n")
    for rid, было, стало in смена:
        c.execute("UPDATE recipients SET email=?, domain=?, updated_at=? WHERE id=?", (стало, стало.split("@")[-1], т, rid))
        ids.append(rid)
        ж.write(json.dumps({"что": "адрес", "id": rid, "bylo": было, "stalo": стало}, ensure_ascii=False) + "\n")
json.dump(ids, io.open(r"C:\sender\_ops\spisok-v4-dobor.json", "w"))
print("ПРИМЕНЕНО, в списке:", len(ids))
