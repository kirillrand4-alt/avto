# -*- coding: utf-8 -*-
"""Залить 46 компаний «Цербер вне ФСА» под Meyer (владелец 22.10: «цербер 46
штук поставь на генерацию»). Вход с дропа: cerber-godnye.json (из
cerber_sverka.py: ИНН, название, вид предприятия, лучший адрес) и
cerber-inns.json (лист файла). Получатель: группы «ФСА волна 1» (её берут
проба и запуск кампании 18) + «ФСА Цербер», сегмент meyer, target_division
meyer, паспорт — вид предприятия по Церберу + деятельность из обогащения.
Пишет _ops/spisok-cerber.json (id) для генерации. Журнал cerber-zaliv.jsonl.
Без --primenit — счёт."""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

import requests

У = os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/")
H = {"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}
годные = requests.get(У + "/cerber-godnye.json", headers=H, timeout=60).json()
лист = requests.get(У + "/cerber-inns.json", headers=H, timeout=60).json()
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=120)
кол_c = [r[1] for r in e.execute("PRAGMA table_info(companies)")]
поля = [k for k in ("name", "okved", "activity", "site", "revenue_rub", "region") if k in кол_c]
ГР = ["ФСА волна 1", "ФСА Цербер"]
т = time.strftime("%Y-%m-%dT%H:%M:%S")
сч = Counter()
ids = []
ж = io.open(r"C:\sender\_ops\cerber-zaliv.jsonl", "a", encoding="utf-8")
for inn, имя, вид, (адр, откуда, проба) in годные:
    к = dict(zip(поля, e.execute("SELECT %s FROM companies WHERE inn=?" % ",".join(поля), (inn,)).fetchone() or [None] * len(поля)))
    л = лист.get(inn) or {}
    пасп = {"Цербер": вид, "адрес объекта (Цербер)": л.get("region")}
    if к.get("activity"):
        пасп["деятельность"] = str(к["activity"])[:600]
    extra = {"gruppy": ГР, "istochnik": "FSA-MEYER-v4-Meyer_1.xlsx, лист «Цербер вне ФСА»", "volna": "cerber",
             "target_division": "meyer", "target_division_istochnik": "Цербер, владелец 22.10", "dolzhnost": откуда,
             "site": к.get("site"), "revenue_rub": к.get("revenue_rub"), "pasport_fsa": пасп}
    r = c.execute("SELECT id, inn, extra_json FROM recipients WHERE lower(email)=?", (адр,)).fetchone()
    if r:
        if str(r[1] or "") != inn:
            сч["адрес в панели под другим ИНН — пропуск"] += 1
            continue
        x = json.loads(r[2] or "{}")
        ж.write(json.dumps({"что": "было", "id": r[0], "extra": r[2]}, ensure_ascii=False) + "\n")
        x["gruppy"] = list(dict.fromkeys(list(x.get("gruppy") or []) + ГР))
        for k in ("target_division", "volna", "pasport_fsa"):
            x.setdefault(k, extra[k])
        x["division"] = "meyer"
        if "--primenit" in sys.argv:
            c.execute("UPDATE recipients SET extra_json=?, updated_at=? WHERE id=?", (json.dumps(x, ensure_ascii=False), т, r[0]))
        ids.append(r[0])
        сч["адрес уже в панели — дописаны группы"] += 1
        continue
    сч["новый получатель"] += 1
    if "--primenit" in sys.argv:
        cur = c.execute("INSERT INTO recipients (email, domain, inn, company_name, okved, segment, source, region, tz, extra_json,"
                        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (адр, адр.split("@")[-1], inn, к.get("name") or л.get("name") or имя, к.get("okved"), "meyer", "fsa-cerber",
                         л.get("region"), "Europe/Moscow", json.dumps({k: v for k, v in extra.items() if v}, ensure_ascii=False), т, т))
        ids.append(cur.lastrowid)
        ж.write(json.dumps({"что": "новый", "id": cur.lastrowid, "email": адр, "inn": inn}, ensure_ascii=False) + "\n")
c.commit()
ж.close()
print(dict(сч))
if "--primenit" in sys.argv:
    json.dump(ids, io.open(r"C:\sender\_ops\spisok-cerber.json", "w"))
    print("ПРИМЕНЕНО, в списке генерации:", len(ids))
else:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
