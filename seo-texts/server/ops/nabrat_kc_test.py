# -*- coding: utf-8 -*-
"""Группа «КЦ тест» из файла владельца KC-1-TEST-otbor.xlsx (15.10: «заведи группу
КЦ тест»). Адрес — колонка «Письмо: e-mail» (выбор отбора), иначе e-mail ЛПР, иначе
лучший живой из обогащения. Мимо: отвечали нам, стоп ИНН, сделка КЦ в работе,
адрес мёртв по пробе/в стоп-листе. division=kc, группа в extra_json.gruppy.
Журнал _ops/gruppa-kc-test.jsonl (fsync).

    nabrat_kc_test.py [--primenit]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.sdelki_napr import blok  # noqa: E402

ПРИМ = "--primenit" in sys.argv
ГРУППА = "КЦ тест"
список = json.load(io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "kc_test_spisok.json"), encoding="utf-8"))
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
отвечали = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
мёртв = {str(r[0]).lower() for r in c.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
мёртв |= {str(r[0]).lower() for r in e.execute("SELECT email FROM emails WHERE probe_verdict IN ('нет ящика','нет MX')")}
стоп_п = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression WHERE scope='email'")}
стоп_д = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression WHERE scope='domain'")}
стоп_и = {str(r[0]) for r in c.execute("SELECT value FROM suppression WHERE scope='inn'")}


def годен(а):
    return bool(а) and "@" in а and а not in мёртв and а not in стоп_п and а.split("@")[-1] not in стоп_д


св, набор = Counter(), []
for к in список:
    инн = к["inn"]
    if инн in отвечали:
        св["мимо: отвечали нам"] += 1
        continue
    if инн in стоп_и:
        св["мимо: стоп ИНН"] += 1
        continue
    if blok(c, инн, "kc"):
        св["мимо: сделка КЦ в работе"] += 1
        continue
    адрес = к["email"] if годен(к["email"]) else ""
    if not адрес:
        for (а,) in e.execute("SELECT lower(email) FROM emails WHERE inn=? AND COALESCE(mx_ok,1)!=0", (инн,)):
            if годен(а):
                адрес = а
                break
    if not адрес:
        св["мимо: нет живого адреса"] += 1
        continue
    св["в группу" + ("" if адрес == к["email"] else " (адрес из обогащения)")] += 1
    набор.append((к, адрес))
print("в файле: %d" % len(список))
for кл, n in св.most_common():
    print("   %-40s %5d" % (кл, n))
сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
нов = обн = 0
ж = io.open(r"C:\sender\_ops\gruppa-kc-test.jsonl", "a", encoding="utf-8") if ПРИМ else None
for к, адрес in набор:
    доп = {"gruppy": [ГРУППА], "division": "kc", "istochnik": "KC-1-TEST-otbor 15.10"}
    for кл, зн in (("contact_name", к.get("fio")), ("role", к.get("dolzh") or к.get("rol")), ("site", к.get("sait"))):
        if зн:
            доп[кл] = зн
    ряд = c.execute("SELECT id, extra_json FROM recipients WHERE lower(email)=?", (адрес,)).fetchone()
    if ряд is None:
        нов += 1
        if ПРИМ:
            c.execute("INSERT INTO recipients (inn,email,domain,company_name,okved,segment,source,region,extra_json,"
                      "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (к["inn"], адрес, адрес.split("@")[-1], к["name"], к.get("okved") or "", к.get("segment") or "",
                       "kc-test-15.10", к.get("region") or "", json.dumps(доп, ensure_ascii=False), сейчас, сейчас))
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
            for кл, зн in доп.items():
                if кл != "gruppy" and кл != "division":
                    стар.setdefault(кл, зн)
            стар["gruppy"] = гр
            c.execute("UPDATE recipients SET extra_json=?, updated_at=? WHERE id=?",
                      (json.dumps(стар, ensure_ascii=False), сейчас, ряд["id"]))
    if ПРИМ:
        ж.write(json.dumps({"inn": к["inn"], "email": адрес, "novyy": ряд is None}, ensure_ascii=False) + "\n")
if ПРИМ:
    c.commit()
    ж.flush()
    os.fsync(ж.fileno())
print("в группу «%s»: %d (новых получателей %d, уже были %d)" % (ГРУППА, len(набор), нов, обн))
print("=== КЦ ТЕСТ: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
