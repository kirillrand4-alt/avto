# -*- coding: utf-8 -*-
"""Как приоритет считается на самом деле: разбираем по слагаемым, а не по названию.

ПОВОД. Владелец спрашивает, почему формула нелогична, если цель — чтобы предприятие КУПИЛО.
Отвечать надо по слагаемым: поле `prioritet_pochemu` в панели хранит разбор словами, и по
нему видно и вес каждого признака, и — главное — чего в формуле НЕТ.
"""
import collections
import json
import re
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
slagaemye = collections.Counter()
ves = {}
for (p,) in cx.execute("select coalesce(prioritet_pochemu,'') from company where "
                       "coalesce(prioritet_pochemu,'') <> ''"):
    for ch in p.split('|'):
        ch = ch.strip()
        if not ch:
            continue
        m = re.match(r'(.+?)\s*([+-]\d+)$', ch)
        if m:
            slagaemye[m.group(1).strip()] += 1
            ves[m.group(1).strip()] = int(m.group(2))
        else:
            slagaemye[ch] += 1
o = {'слагаемые': [[k, ves.get(k), n] for k, n in slagaemye.most_common(20)]}
o['разных_формул'] = cx.execute(
    "select count(distinct prioritet_pochemu) from company").fetchone()[0]
# Есть ли в формуле хоть что-то про возможность позвонить и про срок ЭПБ.
o['формул_со_словом_телефон'] = cx.execute(
    "select count(*) from company where lower(coalesce(prioritet_pochemu,'')) like '%телефон%' "
    "or lower(coalesce(prioritet_pochemu,'')) like '%контакт%'").fetchone()[0]
o['формул_со_словом_срок_ЭПБ'] = cx.execute(
    "select count(*) from company where lower(coalesce(prioritet_pochemu,'')) like '%эпб%' "
    "or lower(coalesce(prioritet_pochemu,'')) like '%истек%' "
    "or lower(coalesce(prioritet_pochemu,'')) like '%срок%'").fetchone()[0]
# Верх очереди: что там на самом деле.
o['верх_очереди'] = cx.execute("""
    select coalesce(vazhnost_pokupki,0), coalesce(prioritet_pochemu,''),
           (select count(*) from person p where p.inn = c.inn
              and coalesce(p.phone,'') <> '') as tel
    from company c order by coalesce(vazhnost_pokupki,0) desc limit 8""").fetchall()
print(json.dumps(o, ensure_ascii=False, indent=1))
