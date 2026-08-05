# -*- coding: utf-8 -*-
"""Показать ВСЕХ людей предприятия с их источниками — чтобы посмотреть глазами.

Владелец отметил на карточке ещё один крест: человек работает в ДОМЕ КУЛЬТУРЫ, а не на
предприятии. Счётчиком такое не ловится: должность у него правдоподобная, привязка
формально есть, и в витрине он неотличим от настоящего. Ловится только чтением —
источником, ссылкой и тем, что вокруг имени стояло на странице.

Прибор печатает по каждому человеку всё, на чём он держится: должность, источник,
ссылку и признак принадлежности. Ничего не фильтрует: задача не отобрать, а ПОКАЗАТЬ.
"""
import json
import re
import sqlite3
import sys

BAZA = 'file:C:/seostat/data/centrifugal.db?mode=ro'
# Слова, по которым видно, что место работы НЕ промышленное предприятие.
NE_ZAVOD = re.compile(
    r'дом\w*\s+культур|дк\b|двор\w*\s+культур|школ|детск|больниц|поликлиник|музе|'
    r'библиотек|театр|спорт|стадион|бассейн|санатор|профилактор|церк|храм|'
    r'администраци\w*\s+(?:город|район|сельс)|управляющ\w*\s+компани|тсж|жкх', re.I)

imya_ili_inn = sys.argv[1] if len(sys.argv) > 1 else 'ТЕХУГЛЕРОД'
b = sqlite3.connect(BAZA, uri=True)
polya = [r[1] for r in b.execute('pragma table_info(person)')]

# Предприятие ищу по ИНН или по куску названия — что дали, то и ищем.
if imya_ili_inn.isdigit():
    usl, par = 'p.inn = ?', (imya_ili_inn,)
else:
    usl, par = 'upper(c.predpriyatie) like ?', ('%' + imya_ili_inn.upper() + '%',)

try:
    stroki = list(b.execute(
        'select c.inn, c.predpriyatie, %s from person p join company c on c.inn = p.inn '
        'where %s' % (','.join('p.' + x for x in polya), usl), par))
except Exception as e:  # noqa: BLE001
    print('запрос не прошёл: %s' % e)
    stroki = []

podozritelnye = 0
for r in stroki:
    inn, nazv = r[0], r[1]
    z = dict(zip(polya, r[2:]))
    ist = str(z.get('source') or '')
    url = str(z.get('source_url') or '')
    pos = str(z.get('position') or '')
    chel = str(z.get('person') or '')
    metka = ''
    if NE_ZAVOD.search(pos) or NE_ZAVOD.search(url) or NE_ZAVOD.search(ist):
        metka = '   <-- МЕСТО РАБОТЫ НЕ ЗАВОД'
        podozritelnye += 1
    print('\n%-30s | %s%s' % (chel[:30], pos[:40], metka))
    print('   тел %-18s почта %-28s тех: %s'
          % (str(z.get('phone') or '—'), str(z.get('email') or '—')[:28], z.get('is_tech')))
    print('   источник: %s' % ist[:110])
    print('   ссылка:   %s' % url[:110])

print('ИТОГ ' + json.dumps({'предприятие': (stroki[0][1] if stroki else imya_ili_inn),
                            'людей': len(stroki),
                            'место работы не завод': podozritelnye}, ensure_ascii=False))
