# -*- coding: utf-8 -*-
"""Из чего состоит список КЦ-1 (_ops/spisok-kc1.json): писали ли компании раньше (КЦ когда-либо,
кампания 17, любое письмо вообще), откуда группа (источник получателя), ответы/отказы."""
import collections, io, json, sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
ids = json.load(io.open(r"C:\sender\_ops\spisok-kc1.json"))
кам = {i: n for i, n in c.execute("SELECT id, name FROM campaigns")}
кц = {i for i, n in кам.items() if i in (1, 5, 6, 9, 10) or "КЦ" in str(n)}
инн_адр = {}
for rid, inn, em, src in c.execute("SELECT id, inn, lower(email), source FROM recipients"):
    инн_адр[rid] = (str(inn or ""), em, src)
писали = collections.defaultdict(set)
for inn, cid in c.execute("SELECT r.inn, m.campaign_id FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'"):
    писали[str(inn or "")].add(cid)
ответ = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint')")}
сч = collections.Counter(); ист = collections.Counter()
for rid in ids:
    inn, em, src = инн_адр.get(rid, ("", "", ""))
    ист[src] += 1
    к = писали.get(inn, set())
    if 17 in к: сч["КЦ-1 уже писали (>30 дн.)"] += 1
    elif к & кц: сч["другая кампания КЦ писала (>30 дн.)"] += 1
    elif к: сч["писали только Meyer"] += 1
    else: сч["НИКОГДА не писали"] += 1
    if inn in ответ: сч["  из них уже отвечали нам"] += 1
print("в списке:", len(ids))
for k, v in сч.most_common(): print("  %-40s %d" % (k, v))
print("источник получателя:", ист.most_common(6))
