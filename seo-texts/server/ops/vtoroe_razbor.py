# -*- coding: utf-8 -*-
"""Куда делись компании кампании для второго касания: vtoroe_razbor.py <campaign_id>.
Только чтение. Разрез каждой компании, которой кампания отправила письмо."""
import json
import re
import sqlite3
import sys
from collections import Counter
cid = int(sys.argv[1])
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
мей = [r[0] for r in c.execute("SELECT id, name FROM campaigns") if "meyer" in str(r[1]).lower()]
q = ",".join(map(str, мей))
комп = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                     "WHERE m.campaign_id=? AND m.status='sent' AND r.inn IS NOT NULL", (cid,))}
отв = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id "
                                    "WHERE e.event_type IN ('reply','reply_auto','complaint','dsn','bounce') AND r.inn IS NOT NULL")}
отв |= {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
писали = {r[0] for r in c.execute("SELECT DISTINCT lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                  "WHERE m.status IN ('sent','scheduled','sending','pending_review')")}
проба = {r[0].lower(): r[1] for r in c.execute("SELECT email, verdict FROM addr_probe")}
стоп = {(a, b.lower()) for a, b in c.execute("SELECT scope, value FROM suppression")}
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=90)
адреса = {}
for inn, em in e.execute("SELECT inn, lower(email) FROM emails"):
    адреса.setdefault(str(inn), set()).add(em)
ит = Counter()
for инн in комп:
    if инн in отв:
        ит["ответ/автоответ/отбивка/лид"] += 1
        continue
    адр_мей = {r[0] for r in c.execute("SELECT DISTINCT lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                        "WHERE r.inn=? AND m.campaign_id IN (%s) AND m.status IN ('sent','scheduled','sending','pending_review')" % q, (инн,))}
    if len(адр_мей) >= 2:
        ст = dict(c.execute("SELECT m.status, COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                            "WHERE r.inn=? AND m.campaign_id=13 GROUP BY m.status", (инн,)).fetchall())
        if "sent" in ст:
            ит["второе касание ОТПРАВЛЕНО"] += 1
        elif "pending_review" in ст:
            ит["второе касание ждёт одобрения"] += 1
        elif ст:
            ит["второе касание в очереди (%s)" % ",".join(ст)] += 1
        else:
            ит["2+ адреса уже в других кампаниях"] += 1
        continue
    запас = {a for a in адреса.get(инн, ()) if a not in писали}
    if not запас:
        ит["нет другого адреса вообще"] += 1
        continue
    ст = []
    for a in запас:
        в = проба.get(a, "")
        if ("email", a) in стоп or ("domain", a.split("@")[-1]) in стоп:
            ст.append("стоп")
        elif в in ("нет ящика", "нет MX"):
            ст.append("мёртв")
        elif в in ("есть", "принимает всё"):
            ст.append("живой")
        elif в:
            ст.append("неясно")
        else:
            ст.append("не проверен")
    for k in ("живой", "не проверен", "неясно", "мёртв", "стоп"):
        if k in ст:
            ит["другой адрес есть, лучший: " + k] += 1
            break
print("компаний, которым кампания %d отправила письмо: %d" % (cid, len(комп)))
for k, n in ит.most_common():
    print("  %5d  %s" % (n, k))
