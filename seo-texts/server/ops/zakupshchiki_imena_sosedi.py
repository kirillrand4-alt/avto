# -*- coding: utf-8 -*-
"""Для компаний КЦ, где закупщик «без имени»: есть ли ИМЕНОВАННЫЙ закупщик той же компании в
соседних таблицах (phone_contacts, people, imena, eis_arch, emails другим адресом)."""
import collections, io, json, re, sqlite3
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
ЗАК = re.compile(r"снабж|закуп|тендер|\bмтс\b|омтс|контрактн|логист", re.I)
инн = set()
for с in io.open(r"C:\sender\_ops\zakupshchiki-imena.jsonl", encoding="utf-8"):
    з = json.loads(с)
    if з["napr"] == "КЦ" and з["reshenie"].startswith("без"): инн.add(з["inn"])
print("компаний КЦ с закупщиком без имени:", len(инн))
нашли = collections.defaultdict(set); пр = {}
for t, q in [("phone_contacts", "SELECT inn, person, COALESCE(role,''), phone FROM phone_contacts WHERE person IS NOT NULL AND trim(person)!=''"),
             ("people", "SELECT inn, person, COALESCE(post,'')||' '||COALESCE(role,''), COALESCE(email,phone) FROM people"),
             ("imena", "SELECT inn, person, COALESCE(post,'')||' '||COALESCE(role,''), email FROM imena"),
             ("eis_arch", "SELECT inn, person, COALESCE(post,'')||' '||COALESCE(role,''), COALESCE(email,phone) FROM eis_arch"),
             ("emails", "SELECT inn, person, COALESCE(role,'')||' '||COALESCE(zahod_rol,''), email FROM emails WHERE person IS NOT NULL AND trim(person)!=''")]:
    for i, p, роль, к in e.execute(q):
        i = str(i)
        if i in инн and ЗАК.search(роль or ""):
            нашли[t].add(i)
            пр.setdefault(t, (p, роль[:40], к))
все = set().union(*нашли.values()) if нашли else set()
for t, v in нашли.items(): print("  %-15s компаний %d  пример: %s" % (t, len(v), пр[t]))
print("итого компаний, где имя закупщика есть хоть где-то:", len(все))
