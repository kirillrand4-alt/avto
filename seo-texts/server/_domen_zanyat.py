# -*- coding: utf-8 -*-
r"""Почему поиск отбрасывает 215 находок из 500 как «домен занят другим ИНН».

Заслон правильный сам по себе: домен, уже закреплённый за другой компанией,
кандидатом брать нельзя, иначе тёзки-прилипалы возвращаются каждым обходом.
Но 43% отказов — много, и надо понять, ЧТО именно занято: горстка агрегаторов,
которых просто нет в списке площадок, или честные разные компании.
"""
import json
import os
import re
import sqlite3
import sys

for _p in (r'C:\sender\server',):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL  # noqa: E402

ЛОГ = r'C:\sender\poisk_saytov.jsonl'
BD = r'C:\sender\enrich.db'

# берём хвост журнала — последние находки
хвост = []
разм = os.path.getsize(ЛОГ)
with open(ЛОГ, encoding='utf-8', errors='replace') as f:
    f.seek(max(0, разм - 3000000))
    f.readline()
    for s in f:
        try:
            d = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if d.get('site'):
            хвост.append((str(d['inn']), PL.домен(d['site'])))

c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
занятые = {}
for инн, s, cs in c.execute(
        "select inn, coalesce(site,''), coalesce(cand_site,'') from companies "
        "where coalesce(site,'')<>'' or coalesce(cand_site,'')<>''"):
    for u in (s, cs):
        d = PL.домен(u) if u else ''
        if d:
            занятые.setdefault(d, set()).add(str(инн))
c.close()

счёт, кто = {}, {}
занято = свободно = 0
for инн, дом in хвост:
    чьи = занятые.get(дом) or set()
    if чьи - {инн}:
        занято += 1
        счёт[дом] = счёт.get(дом, 0) + 1
        кто[дом] = len(чьи)
    else:
        свободно += 1

топ = sorted(счёт.items(), key=lambda x: -x[1])[:15]
print(json.dumps({
    'находок_в_хвосте': len(хвост),
    'занято': занято, 'свободно': свободно,
    'топ_занятых': [{'домен': d, 'сколько_раз_вернул_поиск': n,
                     'за_сколькими_инн_закреплён': кто[d],
                     'в_списке_площадок': bool(PL.из_списка(d))} for d, n in топ],
}, ensure_ascii=False, indent=1))
