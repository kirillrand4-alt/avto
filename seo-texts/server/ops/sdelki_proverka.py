# -*- coding: utf-8 -*-
"""Активные сделки по направлениям против наших писем (владелец 20.10: «из
генерации КЦ исключены активные сделки?»). Таблица sdelki_napr: сколько строк,
свежесть; пересечение с КЦ-1 (список), с письмами кампании 17 в работе и
отправленными, со списком второго касания Meyer."""
import io
import json
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
print("sdelki_napr: строк %s, kc=1: %s, meyer=1: %s, sc=1: %s, свежесть %s..%s" % c.execute(
    "SELECT COUNT(*), SUM(kc), SUM(meyer), SUM(sc), MIN(ts), MAX(ts) FROM sdelki_napr").fetchone())
кц = {r[0] for r in c.execute("SELECT inn FROM sdelki_napr WHERE kc=1")}
мей = {r[0] for r in c.execute("SELECT inn FROM sdelki_napr WHERE meyer=1")}
спис = json.load(io.open(r"C:\sender\_ops\spisok-kc1.json"))
инн_спис = {str(r[0]) for r in c.execute("SELECT inn FROM recipients WHERE id IN (%s)" % ",".join(map(str, спис)))}
print("КЦ-1 список: компаний %d, со сделкой КЦ в работе: %d" % (len(инн_спис), len(инн_спис & кц)))
for st in ("pending_review", "scheduled", "sent"):
    инн = {str(r[0]) for r in c.execute("SELECT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                        "WHERE m.campaign_id IN (15,16,17) AND m.status=?", (st,))}
    print("письма КЦ (кампании 15-17) %-14s компаний %5d, со сделкой КЦ: %d %s" % (st, len(инн), len(инн & кц), sorted(инн & кц)[:8]))
try:
    вк = json.load(io.open(r"C:\sender\_ops\meyer-vtoroe-kasanie.json", encoding="utf-8"))
    инн = {x["inn"] for x in вк}
    print("второе касание Meyer: компаний %d, со сделкой Meyer: %d %s" % (len(инн), len(инн & мей), sorted(инн & мей)[:8]))
except Exception as е:  # noqa: BLE001
    print("второе касание:", е)
