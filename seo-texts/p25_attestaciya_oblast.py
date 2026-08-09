# -*- coding: utf-8 -*-
"""Ответ 1-й сессии на прямой вопрос: лежит ли ОБЛАСТЬ аттестации в тех же строках, что ФИО.

Она спрашивает по делу: если область (Б.7 газораспределение, Б.8 оборудование под
давлением) лежит рядом с человеком, то это факт «у предприятия есть ОПО с нашей машиной»
без единого сетевого запроса. Проверяю на живой базе, а не по памяти.

Только чтение.
"""
import collections
import json
import re
import sqlite3

OBLAST = re.compile(r'\bБ\.?\s?(\d{1,2})(?:\.(\d{1,2}))?', re.I)
NASHE = re.compile(r'давлени|компрессор|газопотреблен|газораспределен|воздухоразделен|'
                   r'криоген|сосуд\w*\s+под|трубопровод\w*\s+пара|азот|кислород', re.I)

cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
for t in ('people', 'phone_contacts'):
    kol = [r[1] for r in cx.execute('pragma table_info(%s)' % t)]
    sel = ','.join('"%s"' % k for k in kol)
    sch = collections.Counter()
    obl = collections.Counter()
    primery = []
    for r in cx.execute('select %s from "%s"' % (sel, t)):
        d = dict(zip(kol, r))
        ist = str(d.get('source') or '')
        if not re.search(r'аттестац|ростехнадзор|\bРТН\b|промбез', ist + ' ' +
                         str(d.get('source_url') or ''), re.I):
            continue
        sch['всего строк аттестации'] += 1
        vse = ' '.join(str(v or '') for v in r)
        m = OBLAST.findall(vse)
        if m:
            sch['ОБЛАСТЬ НАЙДЕНА в строке'] += 1
            for a, b in m:
                obl['Б.%s%s' % (a, ('.' + b) if b else '')] += 1
        if NASHE.search(vse):
            sch['наша тема в строке (давление/газ/компрессор)'] += 1
            if len(primery) < 8:
                primery.append(d)
        if str(d.get('inn') or '').strip():
            sch['с ИНН'] += 1
    print('\n=== %s' % t)
    for k, v in sch.most_common():
        print('  %-46s %6d' % (k, v))
    if obl:
        print('  --- какие области встречаются')
        for k, v in obl.most_common(14):
            print('      %-10s %5d' % (k, v))
    for d in primery[:5]:
        print('  · %s' % json.dumps({k: str(v)[:110] for k, v in d.items() if v},
                                    ensure_ascii=False)[:420])
cx.close()
print('\nИТОГ {"смотрела": "область аттестации рядом с ФИО"}')
