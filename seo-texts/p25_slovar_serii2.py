# -*- coding: utf-8 -*-
"""СЛОВАРЬ, серии: второй заход. Проба нашла в приборе ДВЕ ошибки, обе мои.

ОШИБКА 1 — одна колонка на две оси. Проба ждала у «ТВ-80-1» класс «воздуходувка», вышел
«центробежный». Посмотрела цитату:

    «Турбовоздуходувка ТВ-80-1,6 поз. 7/2, зав. № 1987 … центробежная воздух»

Документ прав, а прибор нет: ТВ-80-1,6 — это центробежная ВОЗДУХОДУВКА. «Центробежный» —
это ПРИНЦИП, «воздуходувка» — ВИД машины. Я свалила их в одно поле, и принцип побеждал вид
просто потому, что стоял выше в списке. Развожу на две колонки.

ОШИБКА 2 — в словарь набежало чужое, и счётчик этого не показал. Глазами:

    Ц4-70   213 встреч, 19 ИНН, «класс центробежный»
            цитата: «ВЕНТИЛЯТОР Ц4-70 №8, поз. В-35»        <- радиальный вентилятор
    КЦ-2    135 встреч, цитата: «здание – укрытие газоперекачивающего агрегата КЦ-2»
                                                             <- компрессорный ЦЕХ, не машина
    ЦК-1    163 встреч, цитата: «компрессор типа К-250-61-5, ПОЗ. ЦК-1»
                                                             <- позиция на схеме, не серия

Три разных вида мусора: чужая машина, помещение, позиционное обозначение. Ставлю три
заслона и печатаю, сколько каждый снял, — иначе «984 серии» это число, в котором никто не
разберётся.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import json
import os
import re
import sqlite3

ISTOCHNIKI = [(r'C:\seostat\data\centrifugal.db', 'fact'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'tenders'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'fakty')]

SERIYA = re.compile(
    r'\b((?:ТВ|ЦК|ЦНД|К|КТК|ВЦ|ЗИФ|НВЭ|ВП|ВМ|ПКС|ЭК|АК|ТГ|ГПА|АДГ|ВК|КР|УКС|ВШ|ТКА|Ц)'
    r'[- ]?\d{1,4}(?:[-/][\dА-Яа-яA-Za-z,\.]{1,8}){0,3})\b', re.U)

PRINCIP = (('центробежный', re.compile(r'центробежн|турбо', re.I)),
           ('винтовой', re.compile(r'винтов', re.I)),
           ('поршневой', re.compile(r'поршнев', re.I)),
           ('мембранный', re.compile(r'мембранн', re.I)))
VID = (('воздуходувка', re.compile(r'воздуходув|газодув', re.I)),
       ('нагнетатель', re.compile(r'нагнетател', re.I)),
       ('ВРУ / разделение воздуха', re.compile(r'воздухоразделен|\bВРУ\b|криоген', re.I)),
       ('генератор азота/кислорода', re.compile(r'генератор\w*\s+(?:азота|кислорода)|'
                                                r'азотн\w+\s+станци|кислородн\w+\s+станци', re.I)),
       ('МКС / передвижная', re.compile(r'\bМКС\b|передвижн\w+\s+компрессор|'
                                        r'мобильн\w+\s+компрессор', re.I)),
       ('осушитель', re.compile(r'осушител', re.I)),
       ('ГПА', re.compile(r'газоперекачивающ|\bГПА\b', re.I)),
       ('компрессор', re.compile(r'компрессор', re.I)))

# --- три заслона, каждый на свой вид мусора -----------------------------------------
CHUZHAYA_MASHINA = re.compile(r'вентилятор|дымосос|\bнасос\w*\b|градирн|конвейер|'
                              r'кондиционер|трактор|сельхоз|автотранспорт|стартер|'
                              r'John Deere|New Holland|MacDon', re.I)
POMESHCHENIE = re.compile(r'здани|укрыти|помещени|цех\b|корпус|площадк\w+\s+КС|станци\w+\s+КС', re.I)
POZICIYA = re.compile(r'поз\.?\s*$|позици\w*\s*$|№\s*$', re.I)

serii = collections.defaultdict(lambda: {'v': 0, 'p': collections.Counter(),
                                         'vid': collections.Counter(), 'inn': set(),
                                         'cit': [], 'srez': collections.Counter()})
prosmotr = collections.Counter()
snyato = collections.Counter()

for baza, tabl in ISTOCHNIKI:
    if not os.path.exists(baza):
        continue
    cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
    kol = [r[1] for r in cx.execute('pragma table_info("%s")' % tabl)]
    if not kol:
        cx.close()
        continue
    sel = ','.join('"%s"' % k for k in kol)
    pinn = 'inn' if 'inn' in kol else None
    for r in cx.execute('select %s from "%s"' % (sel, tabl)):
        d = dict(zip(kol, r))
        tekst = ' '.join(str(v) for v in r if v is not None)
        if len(tekst) < 8:
            continue
        prosmotr['%s.%s' % (os.path.basename(baza), tabl)] += 1
        for m in SERIYA.finditer(tekst):
            s = re.sub(r'\s+', '', m.group(1)).upper()
            do = tekst[max(0, m.start() - 60):m.start()]
            okno = tekst[max(0, m.start() - 120):m.end() + 120]
            z = serii[s]
            if POZICIYA.search(do):
                z['srez']['позиция на схеме'] += 1
                snyato['позиция на схеме'] += 1
                continue
            if CHUZHAYA_MASHINA.search(okno):
                z['srez']['чужая машина'] += 1
                snyato['чужая машина'] += 1
                continue
            if POMESHCHENIE.search(okno) and not re.search(r'компрессор|воздуходув|нагнетател', okno, re.I):
                z['srez']['помещение'] += 1
                snyato['помещение'] += 1
                continue
            z['v'] += 1
            for imya, rg in PRINCIP:
                if rg.search(okno):
                    z['p'][imya] += 1
                    break
            for imya, rg in VID:
                if rg.search(okno):
                    z['vid'][imya] += 1
                    break
            if pinn and str(d.get(pinn) or '').strip():
                z['inn'].add(str(d[pinn]).strip())
            if len(z['cit']) < 2:
                z['cit'].append(re.sub(r'\s+', ' ', okno)[:150])
    cx.close()

itog = {}
for s, z in serii.items():
    if z['v'] < 2:
        continue
    itog[s] = {'встреч': z['v'], 'ИНН': len(z['inn']),
               'принцип': (z['p'].most_common(1) or [('не установлен', 0)])[0][0],
               'вид': (z['vid'].most_common(1) or [('не установлен', 0)])[0][0],
               'снято_заслонами': dict(z['srez']),
               'цитата': z['cit'][0] if z['cit'] else ''}

PROBA = [('ТВ-80-1,6', 'центробежный', 'воздуходувка'),
         ('К-250-61-1', 'центробежный', 'компрессор'),
         ('ЦК135/8', 'центробежный', 'компрессор'),
         ('Ц4-70', None, None)]
provaly = []
for s, pr, vd in PROBA:
    k = s.replace(' ', '').upper()
    if pr is None:
        if k in itog and itog[k]['встреч'] > 20:
            provaly.append('%s должна быть отсеяна как вентилятор, а осталась (%d встреч)'
                           % (s, itog[k]['встреч']))
        continue
    if k not in itog:
        provaly.append('НЕ НАЙДЕНА %s' % s)
        continue
    if itog[k]['принцип'] != pr:
        provaly.append('%s принцип: ждали «%s», вышло «%s»' % (s, pr, itog[k]['принцип']))
    if itog[k]['вид'] != vd:
        provaly.append('%s вид: ждали «%s», вышло «%s»' % (s, vd, itog[k]['вид']))

print('\n\n########## ПЯТНАДЦАТЬ СЕРИЙ ГЛАЗАМИ')
for s, z in sorted(itog.items(), key=lambda x: -x[1]['встреч'])[:15]:
    print('\n  %-14s встреч %5d  ИНН %4d  принцип: %-14s вид: %s'
          % (s, z['встреч'], z['ИНН'], z['принцип'], z['вид']))
    if z['снято_заслонами']:
        print('      заслоны сняли: %s' % z['снято_заслонами'])
    print('      %s' % z['цитата'][:140])

print('\n\n########## ПРОБА')
for p in provaly:
    print('  ПРОВАЛ: %s' % p)
print('  провалов %d' % len(provaly))

print('\n########## ЧИСЛА')
for k, v in prosmotr.most_common():
    print('  просмотрено %-32s %7d' % (k, v))
print('  серий в словаре (встреч >= 2)    %6d' % len(itog))
print('  --- по принципу')
for k, v in collections.Counter(z['принцип'] for z in itog.values()).most_common():
    print('     %-30s %5d' % (k, v))
print('  --- по виду')
for k, v in collections.Counter(z['вид'] for z in itog.values()).most_common():
    print('     %-30s %5d' % (k, v))
print('  --- снято заслонами (упоминаний)')
for k, v in snyato.most_common():
    print('     %-30s %5d' % (k, v))
print('ИТОГ ' + json.dumps({'серий': len(itog), 'провалов': len(provaly),
                            'снято': dict(snyato)}, ensure_ascii=False))
