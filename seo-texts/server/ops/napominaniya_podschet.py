# -*- coding: utf-8 -*-
"""Сколько компаний Meyer подходит для напоминания в ветку (владелец 23.10:
«скольким компаниям мы писали больше чем 15 дней назад по мейер?»).
Только чтение. По ИНН: последнее отправленное письмо Meyer старше N дней, и
компании ни на какой её адрес не было: ответа/автоответа/жалобы/отбивки, письма
(любого направления) за последние N дней, лида, стоп-листа по адресу/домену,
приговора пробы («нет ящика»/«нет MX»).
    napominaniya_podschet.py [дней=15]"""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
сейчас = datetime.now(timezone.utc)
порог = (сейчас - timedelta(days=N)).strftime("%Y-%m-%dT%H:%M:%S")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
мк = {k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()}
инн_пол = {}
for rid, inn, em in c.execute("SELECT id, inn, lower(email) FROM recipients"):
    инн_пол[rid] = (str(inn or "") or "rid%d" % rid, em or "")
отправки = {}     # инн -> [(sent_at, campaign, email)]
for rid, cid, sent in c.execute("SELECT recipient_id, campaign_id, sent_at FROM messages WHERE status='sent' AND sent_at IS NOT NULL"):
    инн, em = инн_пол.get(rid, ("rid%d" % rid, ""))
    отправки.setdefault(инн, []).append((sent, cid, em))
плохие_инн = set()
for (rid,) in c.execute("SELECT DISTINCT recipient_id FROM events WHERE event_type IN ('reply','reply_auto','complaint','dsn','bounce')"):
    if rid in инн_пол:
        плохие_инн.add(инн_пол[rid][0])
try:
    for (rid,) in c.execute("SELECT DISTINCT recipient_id FROM leads"):
        if rid in инн_пол:
            плохие_инн.add(инн_пол[rid][0])
except sqlite3.Error:
    pass
стоп = {(s, v.lower()) for s, v in c.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in c.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
итог, причины, по_возрасту, по_камп = 0, Counter(), Counter(), Counter()
for инн, сп in отправки.items():
    мейер = [x for x in сп if x[1] in мк]
    if not мейер:
        continue
    посл = max(x[0] for x in мейер)
    if посл >= порог:
        причины["письмо Meyer моложе %d дней" % N] += 1
        continue
    if max(x[0] for x in сп) >= порог:
        причины["свежее письмо другого направления"] += 1
        continue
    if инн in плохие_инн:
        причины["был ответ/отбивка/жалоба/лид"] += 1
        continue
    em = [x for x in мейер if x[0] == посл][0][2]
    if em in мёртв:
        причины["адрес мёртв по пробе"] += 1
        continue
    if ("email", em) in стоп or ("domain", em.split("@")[-1]) in стоп:
        причины["стоп-лист"] += 1
        continue
    итог += 1
    д = (сейчас - datetime.fromisoformat(посл[:19]).replace(tzinfo=timezone.utc)).days
    по_возрасту["%d-30 дней" % N if д <= 30 else "31-60 дней" if д <= 60 else "больше 60 дней"] += 1
    по_камп[кам.get([x for x in мейер if x[0] == посл][0][1], "?")] += 1
print("компаний Meyer с отправленным письмом:", sum(1 for сп in отправки.values() if any(x[1] in мк for x in сп)))
print("ПОДХОДЯТ для напоминания (последнее письмо старше %d дней): %d" % (N, итог))
print("по давности:", dict(по_возрасту))
print("по кампании последнего письма:")
for к, n in по_камп.most_common(15):
    print("   %5d  %s" % (n, к))
print("отсеяно:", dict(причины))
