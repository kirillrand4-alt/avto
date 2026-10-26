# -*- coding: utf-8 -*-
"""Вернуть в очередь одобренные письма, снятые старым «уже писали», если по
нынешним правилам они проходят (владелец 26.10: «да, делай»; правила 23.10:
другой адрес компании — через 3 дня, тот же адрес — через 30, компания не
отвечала). Окно — решения за N дней. Письмо -> scheduled, время = сейчас.
КЦ после этого ставить в конец — kc_v_konec.py --primenit.
Журнал _ops/vernut-po-pravilam.jsonl; --otkat — обратно в skipped.
    vernut_po_pravilam.py [дней=7] [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta

ЖУР = r"C:\sender\_ops\vernut-po-pravilam.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in з:
            c.execute("UPDATE messages SET status='skipped', last_error=?, scheduled_at=? WHERE id=? AND status='scheduled'",
                      (x["bylo_err"], x["bylo_sched"], x["id"]))
    print("откат:", len(з))
    sys.exit()
N = int(next((a for a in sys.argv[1:] if a.isdigit()), "7"))
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сейчас = datetime.utcnow()
отв = {r[0] for r in c.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id "
                                "WHERE e.event_type IN ('reply','complaint') AND r.inn IS NOT NULL")}
стоп = {(s, v.lower()) for s, v in c.execute("SELECT scope, value FROM suppression")}
ряды = c.execute(
    "SELECT m.id, m.campaign_id, m.scheduled_at, m.last_error, r.inn, lower(r.email) "
    "FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id JOIN recipients r ON r.id=m.recipient_id "
    "WHERE cr.status IN ('approved','edited') AND cr.decided_at >= datetime('now', ?) "
    "AND m.status='skipped' AND m.last_error LIKE 'auto_send:уже писали%'", ("-%d days" % N,)).fetchall()
годные, отсев = [], Counter()
for mid, cid, sa, err, инн, em in ряды:
    тот = c.execute("SELECT MAX(m.sent_at) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                    "WHERE lower(r.email)=? AND m.status='sent'", (em,)).fetchone()[0]
    комп = c.execute("SELECT MAX(m.sent_at) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                     "WHERE r.inn=? AND m.status='sent'", (инн,)).fetchone()[0] if инн else None
    if инн in отв:
        отсев["компания отвечала"] += 1
    elif ("email", em) in стоп or ("domain", em.split("@")[-1]) in стоп:
        отсев["стоп-лист"] += 1
    elif тот and сейчас - datetime.fromisoformat(тот[:19]) < timedelta(days=30):
        отсев["тот же адрес моложе 30 дней"] += 1
    elif комп and сейчас - datetime.fromisoformat(комп[:19]) < timedelta(days=3):
        отсев["компании писали < 3 дней"] += 1
    else:
        годные.append((mid, cid, sa, err))
print("снятых «уже писали»: %d, вернуть: %d, отсев: %s" % (len(ряды), len(годные), dict(отсев)))
print("по кампаниям:", dict(Counter(кам.get(g[1]) for g in годные)))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
т = сейчас.strftime("%Y-%m-%dT%H:%M:%S.%f")
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for mid, cid, sa, err in годные:
        c.execute("UPDATE messages SET status='scheduled', scheduled_at=?, last_error=NULL, updated_at=? "
                  "WHERE id=? AND status='skipped'", (т, т, mid))
        ж.write(json.dumps({"id": mid, "bylo_sched": sa, "bylo_err": err}, ensure_ascii=False) + "\n")
print("ПРИМЕНЕНО:", len(годные))
