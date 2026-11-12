# -*- coding: utf-8 -*-
"""Для подходящих компаний (meyer-provaly.jsonl): писали ли за 60 дней ИМЕННО на адреса из файла контактов сделок,
или на другие адреса той же компании (по ИНН). Раздельно Meyer / КЦ. Только чтение."""
import io, json, re, sqlite3
from collections import Counter
cs = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
по_почте, по_инн = {}, {}
for em, инн, mb, t in cs.execute("SELECT lower(r.email), COALESCE(r.inn,''), m.mailbox_id, substr(m.sent_at,1,10) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                 "WHERE m.status='sent' AND m.sent_at>='2026-09-13'"):
    н = "Meyer" if re.search(r"sort|rentgen|inspection|optic", mb or "") else "КЦ"
    по_почте.setdefault(em, set()).add(н)
    if инн: по_инн.setdefault(инн, set()).add(н)
сч = Counter(); адр = Counter()
for с in io.open(r"C:\sender\_ops\meyer-provaly.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if not x["kat"].startswith("ПОДХОДИТ"): continue
    те = set().union(*[по_почте.get(e, set()) for e in x["emails"]]) if x["emails"] else set()
    для_адр = sum(1 for e in x["emails"] if e in по_почте)
    др = по_инн.get(x["inn"], set()) if x["inn"] else set()
    for н in ("Meyer", "КЦ"):
        if н in те: сч["%s: на адрес из файла" % н] += 1
        elif н in др: сч["%s: только на другой адрес компании" % н] += 1
    адр["адресов из файла, получивших письмо"] += для_адр; адр["адресов из файла всего"] += len(x["emails"])
print(dict(сч)); print(dict(адр))
