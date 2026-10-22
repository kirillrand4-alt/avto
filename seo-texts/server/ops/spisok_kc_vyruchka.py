# -*- coding: utf-8 -*-
"""Список генерации КЦ по выручке (владелец 22.10: «сразу запускай 1870
компаний на генерацию, а мне скинь список у кого нет данных и отдельный
список 0-30»). Отбор компаний — как в komu_eshche_kc.py: направление КЦ, ещё
не писали и нет письма в работе, нет лида, адрес не в стоп-листе и не мёртв,
лучший адрес «есть»/«принимает всё»/не проверен («неясно»/«отказ» — вон).
  * выручка от 30 млн → _ops/spisok-kc1.json (лучший адрес компании; «есть»
    раньше, внутри — крупные раньше);
  * без выручки и до 30 млн → два CSV на дроп (kc-bez-vyruchki.csv,
    kc-vyruchka-0-30.csv) владельцу посмотреть.
    spisok_kc_vyruchka.py [--suho]"""
import csv
import io
import json
import os
import sqlite3
import sys
from collections import Counter

import requests

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
таб = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
стоп = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
писали = {str(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "WHERE m.status NOT IN ('skipped','failed') AND r.inn IS NOT NULL")}
писали |= {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM send_log WHERE inn IS NOT NULL")}
лиды = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")} if "leads" in таб else set()
кол = [r[1] for r in e.execute("PRAGMA table_info(companies)")]
доп = [k for k in ("site", "okved") if k in кол]
комп_е = {str(r[0]): r[1:] for r in e.execute("SELECT inn, revenue_rub, %s FROM companies" % ",".join(доп))}
РАНГ = {"есть": 0, "принимает всё": 1, "": 2, "неясно": 3, "отказ пробе": 4}
лучший = {}
for rid, em, inn, имя, seg, ex in c.execute("SELECT id, lower(email), inn, company_name, segment, extra_json FROM recipients "
                                             "WHERE inn IS NOT NULL AND inn!=''"):
    x = json.loads(ex or "{}")
    if not (str(seg or "") == "кц" or x.get("target_division") == "kc"):
        continue
    inn = str(inn)
    if inn in писали or inn in лиды or em in стоп:
        continue
    в = проба.get(em, "")
    if в in ("нет ящика", "нет MX"):
        continue
    гр = x.get("gruppy") or []
    ключ = (РАНГ.get(в, 2), 0 if "КЦ-1" in гр else 1, rid)
    if inn not in лучший or ключ < лучший[inn][0]:
        лучший[inn] = (ключ, rid, em, имя, в, гр, x)


def выручка(inn, x):
    р = комп_е.get(inn)
    в = (р and р[0]) or x.get("revenue_rub") or 0
    try:
        return float(в)
    except (TypeError, ValueError):
        return 0.0


ген, нет, мелк = [], [], []
for inn, (ключ, rid, em, имя, в, гр, x) in лучший.items():
    if ключ[0] > 2:
        continue
    vr = выручка(inn, x)
    р = комп_е.get(inn) or (None,) * (1 + len(доп))
    стр = {"ИНН": inn, "компания": имя or "", "адрес": em, "проба": в or "не проверен",
           "выручка_млн": round(vr / 1e6, 1) if vr else "", "группы": ", ".join(гр),
           "ступень": x.get("stupen") or "", "отрасль": x.get("otrasl") or ""}
    for i, k in enumerate(доп):
        стр[k] = р[1 + i] or ""
    if vr >= 3e7:
        ген.append((ключ[0], -vr, rid, гр))
    elif vr:
        мелк.append(стр)
    else:
        нет.append(стр)
ген.sort()
print("к генерации (выручка от 30 млн):", len(ген), "| из них в группе КЦ-1:", sum(1 for g in ген if "КЦ-1" in g[3]))
print("  по группам:", Counter(g for г in ген for g in (г[3] or ["—"])).most_common(6))
print("без выручки:", len(нет), "| до 30 млн:", len(мелк))
if "--suho" in sys.argv:
    raise SystemExit(0)
json.dump([g[2] for g in ген], io.open(r"C:\sender\_ops\spisok-kc1.json", "w"))
# Драйвер берёт только получателей группы «КЦ-1» (gruppa=КЦ-1): остальным из
# списка (Россия 9000, Партия 935…) дописываем группу. Прежний extra — в
# журнал _ops/kc-vyruchka-gruppa.jsonl (откат по нему).
import time
т = time.strftime("%Y-%m-%dT%H:%M:%S")
доб = 0
with c, io.open(r"C:\sender\_ops\kc-vyruchka-gruppa.jsonl", "a", encoding="utf-8") as ж:
    for _, _, rid, гр in ген:
        if "КЦ-1" in гр:
            continue
        ex = c.execute("SELECT extra_json FROM recipients WHERE id=?", (rid,)).fetchone()[0]
        ж.write(json.dumps({"id": rid, "extra": ex}, ensure_ascii=False) + "\n")
        x = json.loads(ex or "{}")
        x["gruppy"] = list(x.get("gruppy") or []) + ["КЦ-1"]
        c.execute("UPDATE recipients SET extra_json=?, updated_at=? WHERE id=?", (json.dumps(x, ensure_ascii=False), т, rid))
        доб += 1
print("группа «КЦ-1» дописана получателям:", доб)
поля = ["ИНН", "компания", "адрес", "проба", "выручка_млн"] + доп + ["отрасль", "ступень", "группы"]
for имя_ф, ряды in (("kc-bez-vyruchki.csv", нет), ("kc-vyruchka-0-30.csv", мелк)):
    ряды.sort(key=lambda s: (-(s["выручка_млн"] or 0), s["компания"]))
    п = os.path.join(r"C:\sender\_ops", имя_ф)
    with io.open(п, "w", encoding="utf-8-sig", newline="") as ф:
        w = csv.DictWriter(ф, поля, delimiter=";")
        w.writeheader()
        w.writerows(ряды)
    r = requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/" + имя_ф,
                     data=open(п, "rb").read(), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=120)
    print("дроп", имя_ф, r.status_code)
