# -*- coding: utf-8 -*-
"""Новая группа Meyer из предкласса вне групп (владелец 14.10: «1-3 делай»).

Берём компании с вердиктом «мейер»/«оба» из прогона «вне групп 14.10», кому ещё
нет письма Meyer (в очереди или отправлено), не «не наш», не отвечали. Адрес —
лучший по лесенке ролей из обогащения (без приговора пробы «нет ящика/нет MX»,
без стоп-листа, без кадров/бухгалтерии/прессы, не отправленный раньше);
есть живой адрес в получателях — берём его. Группа в extra_json.gruppy,
division=meyer. Журнал _ops/gruppa-meyer-vne-grupp.jsonl (fsync).

    nabrat_meyer_vne_grupp.py [--primenit]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
try:
    from lead_scoring import _rol_ball  # noqa: E402
except Exception:  # noqa: BLE001
    def _rol_ball(р):
        return 0

ПРИМ = "--primenit" in sys.argv
ГРУППА = "Meyer вне групп 14.10"
МЁРТВ = ("нет ящика", "нет MX")
НЕ_ДЛЯ = ("кадр", "бухгалт", "пресс", "hr", "не для письма", "резюме", "вакан")
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
e.row_factory = sqlite3.Row
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
МЕЙЕР_К = [r[0] for r in c.execute("SELECT id FROM campaigns WHERE name LIKE '%Meyer%'")]
с_письмом = {str(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id IN (%s) "
    "AND m.status IN ('pending_review','approved','scheduled','sending','sent')" % ",".join(map(str, МЕЙЕР_К)))}
отвечали = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
ушло = {str(r[0]).lower() for r in c.execute(
    "SELECT DISTINCT lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'")}
мёртв = {str(r[0]).lower() for r in c.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
стоп_п = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression WHERE scope='email'")}
стоп_д = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression WHERE scope='domain'")}
стоп_и = {str(r[0]) for r in c.execute("SELECT value FROM suppression WHERE scope='inn'")}
try:
    from sender.ne_nash import build_ne_nash
    не_наш = set(build_ne_nash().набор(None) or [])
except Exception:  # noqa: BLE001
    не_наш = set()

компании = [dict(р) for р in e.execute(
    "SELECT inn, name, okved, region, revenue_rub FROM companies WHERE verdikt_pochemu LIKE '%вне групп 14.10%' "
    "AND verdikt_napr IN ('мейер','оба')")]
св, набор, занятые = Counter(), [], set()


def годен(а):
    а = а.lower()
    return (а and а not in мёртв and а not in стоп_п and а.split("@")[-1] not in стоп_д
            and а not in ушло and а not in занятые)


for к in компании:
    инн = str(к["inn"])
    if инн in с_письмом:
        св["мимо: письмо Meyer уже есть"] += 1
        continue
    if инн in не_наш or инн in стоп_и:
        св["мимо: не наш / стоп ИНН"] += 1
        continue
    if инн in отвечали:
        св["мимо: отвечали"] += 1
        continue
    кандидаты = []
    for р in e.execute("SELECT email, role, probe_verdict, mx_ok FROM emails WHERE inn=?", (инн,)):
        а = str(р["email"] or "").strip().lower()
        if (р["probe_verdict"] or "") in МЁРТВ or р["mx_ok"] == 0:
            continue
        if any(с in str(р["role"] or "").lower() for с in НЕ_ДЛЯ):
            continue
        if годен(а):
            кандидаты.append((-_rol_ball(р["role"]), 0 if р["probe_verdict"] == "есть" else 1, а, р["role"]))
    if not кандидаты:
        for р in c.execute("SELECT email FROM recipients WHERE inn=?", (инн,)):
            а = str(р["email"] or "").strip().lower()
            if годен(а):
                кандидаты.append((0, 1, а, ""))
    if not кандидаты:
        св["мимо: нет живого нового адреса"] += 1
        continue
    кандидаты.sort()
    адрес, роль = кандидаты[0][2], кандидаты[0][3]
    занятые.add(адрес)
    набор.append((к, адрес, роль))
    св["в группу"] += 1
print("компаний Meyer вне групп: %d" % len(компании))
for кл, n in св.most_common():
    print("   %-36s %6d" % (кл, n))
сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
нов = обн = 0
if ПРИМ:
    ж = io.open(r"C:\sender\_ops\gruppa-meyer-vne-grupp.jsonl", "a", encoding="utf-8")
for к, адрес, роль in набор:
    доп = {"gruppy": [ГРУППА], "division": "meyer", "istochnik": "predklass-vne-grupp-14.10"}
    if роль:
        доп["role"] = роль
    ряд = c.execute("SELECT id, extra_json FROM recipients WHERE lower(email)=?", (адрес,)).fetchone()
    if ряд is None:
        нов += 1
        if ПРИМ:
            c.execute("INSERT INTO recipients (inn,email,domain,company_name,okved,segment,source,region,extra_json,"
                      "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (к["inn"], адрес, адрес.split("@")[-1], к["name"], к["okved"], "", "predklass-vne-grupp",
                       к["region"], json.dumps(доп, ensure_ascii=False), сейчас, сейчас))
    else:
        обн += 1
        if ПРИМ:
            try:
                стар = json.loads(ряд["extra_json"] or "{}") or {}
            except Exception:  # noqa: BLE001
                стар = {}
            гр = [str(g) for g in (стар.get("gruppy") or [])]
            if ГРУППА not in гр:
                гр.append(ГРУППА)
            стар.update(доп)
            стар["gruppy"] = гр
            c.execute("UPDATE recipients SET extra_json=?, updated_at=? WHERE id=?",
                      (json.dumps(стар, ensure_ascii=False), сейчас, ряд["id"]))
    if ПРИМ:
        ж.write(json.dumps({"inn": к["inn"], "email": адрес, "novyy": ряд is None}, ensure_ascii=False) + "\n")
if ПРИМ:
    c.commit()
    ж.flush()
    os.fsync(ж.fileno())
    ж.close()
print("в группу «%s»: %d (новых получателей %d, обновлено %d)" % (ГРУППА, len(набор), нов, обн))
print("=== НАБРАТЬ MEYER ВНЕ ГРУПП: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
