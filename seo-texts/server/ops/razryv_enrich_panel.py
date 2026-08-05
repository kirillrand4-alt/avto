# -*- coding: utf-8 -*-
"""Разрыв между хранилищем канала и базой панели.

Обход руководства пишет людей в `enrich.db.people`. Панель обзвона на 8012
читает `centrifugal.db.person`, панель P25 на 8014 — `p25.db.person`. Если
мостика нет, добытое каналом до продавца не доходит: работа сделана, лежит и
не видна.

Считаю разрыв по каждой базе: сколько людей enrich относится к её ИНН и
скольких из них в её таблице нет.
"""
import os, sqlite3, sys
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог','технолог')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','логистик','бухгалтер','склад')

db = EDB.EnrichDB()
люди = []
for и, чел, пост, тел, нл, урл, ист in db.cx.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(post,''), COALESCE(phone,''), "
        "COALESCE(nomer_ne_lichnyy,''), COALESCE(source_url,''), COALESCE(source,'') "
        "FROM people"):
    люди.append((str(и), str(чел), str(пост), str(тел), str(нл), str(урл), str(ист)))
print('людей в enrich.people:', len(люди))

for имя, путь in (('P25', r'C:\seostat\data\p25.db'),
                  ('центробежка', os.getenv('CENTRIFUGAL_DB')
                   or r'C:\seostat\data\centrifugal.db')):
    цб = sqlite3.connect('file:' + путь + '?mode=ro', uri=True)
    инны = {str(и) for и, in цб.execute('SELECT inn FROM company')}
    есть = {(str(и), str(ч).casefold()) for и, ч in
            цб.execute("SELECT inn, COALESCE(person,'') FROM person")}
    цб.close()
    c = Counter()
    for и, чел, пост, тел, нл, урл, ист in люди:
        if и not in инны:
            continue
        c['людей enrich относится к базе'] += 1
        если_есть = (и, чел.casefold()) in есть
        c['   уже в базе панели' if если_есть else '   НЕТ в базе панели'] += 1
        if если_есть:
            continue
        низ = пост.casefold()
        тех = пост and any(x in низ for x in ТЕХ) and not any(x in низ for x in СНАБЖ)
        ц = ''.join(x for x in тел if x.isdigit())[-10:]
        if тех:
            c['      из них технарь по должности'] += 1
            if len(ц) == 10 and ц[0] == '9' and not нл:
                c['      ТЕХНАРЬ + ЛИЧНЫЙ МОБИЛЬНЫЙ, не доехал'] += 1
    print(f'\n=== {имя}')
    for к, v in c.items():
        print(f'   {к:44} {v:6}')
