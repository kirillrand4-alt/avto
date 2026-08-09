# -*- coding: utf-8 -*-
"""Серии НЕ центробежные: винтовые, поршневые, МКС, азот/кислород. Моя же дыра, чиню.

Мой шаблон серий — ТВ|ЦК|К-|КТК|ВЦ|ЗИФ|ГПА — это префиксы советских ЦЕНТРОБЕЖНЫХ машин.
Я взяла их и получила «центробежный 549, винтовой 45, МКС 1». Это не парк страны, это мой
шаблон, отражённый в зеркале.

Достраиваю вторую половину номенклатуры:

    импорт винтовые     GA GX GR ZR ZT ZE XAS XAHS (Atlas Copco), SSR RS ML (Ingersoll),
                        BSD CSD ASD (Kaeser), SK KE (Boge), FST (Fini), СРМ, ES
    отечественные       ВК ВВ ПКС ЗИФ-ПВ ПКСД НВЭ СО-7Б АКР ВП
    передвижные / МКС   МКС ПКС ЗИФ-ПВ ДЭН КВ-10 ПР
    азот / кислород     АГ-, АДС, ТГА, ААР, КГС, КЖ, СКДС, УКА, ГА-, ГК-

Класс машины беру ИЗ ТЕКСТА рядом, как в первом словаре: знание надо доказать документом.
Плюс три заслона (позиция, помещение, чужая машина) — те же, что уже оплачены.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import json
import os
import re
import sqlite3

ISTOCHNIKI = [(r'C:\sender\enrich.db', 'signals'), (r'C:\seostat\data\centrifugal.db', 'fact'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'tenders'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'fakty')]

SEMEYSTVA = [
    ('импорт винтовой', re.compile(
        r'\b(GA|GX|GR|ZR|ZT|ZE|XAS|XAHS|SSR|RS|ML|BSD|CSD|ASD|SK|KE|FST|ES|LT|SF)'
        r'[- ]?\d{1,4}(?:[-/ ]?(?:VSD|FF|AP|W|A|VS))?\b')),
    ('отечественный винтовой/поршневой', re.compile(
        r'\b(ВК|ВВ|ПКС|ПКСД|НВЭ|СО|АКР|ВП|С|К)[- ]?\d{1,3}[А-Яа-яA-Za-z]?'
        r'(?:[-/][\dА-Яа-я,\.]{1,6}){0,2}\b')),
    ('передвижная / МКС', re.compile(
        r'\b(МКС|ЗИФ-ПВ|ЗИФ|ДЭН|ПР|КВ)[- ]?\d{1,3}(?:[-/][\d,\.]{1,6}){0,2}\b')),
    ('азот / кислород', re.compile(
        r'\b(АГ|АДС|ТГА|ААР|КГС|КЖ|СКДС|УКА|ГА|ГК|АКМ|ТКА)[- ]?\d{1,4}'
        r'(?:[-/][\dА-Яа-я,\.]{1,6}){0,2}\b')),
]
VID = (('воздуходувка', re.compile(r'воздуходув|газодув', re.I)),
       ('ВРУ', re.compile(r'воздухоразделен|\bВРУ\b|криоген', re.I)),
       ('генератор азота', re.compile(r'генератор\w*\s+азота|азотн\w+\s+станци|'
                                      r'мембранн\w+\s+азот|адсорбцион\w+\s+азот', re.I)),
       ('генератор кислорода', re.compile(r'генератор\w*\s+кислорода|кислородн\w+\s+станци|'
                                          r'концентратор\w*\s+кислорода', re.I)),
       ('МКС / передвижная', re.compile(r'\bМКС\b|передвижн\w+\s+компрессор|'
                                        r'мобильн\w+\s+компрессор|дизельн\w+\s+компрессор', re.I)),
       ('осушитель', re.compile(r'осушител', re.I)),
       ('компрессор', re.compile(r'компрессор', re.I)))
PRINCIP = (('винтовой', re.compile(r'винтов', re.I)), ('поршневой', re.compile(r'поршнев', re.I)),
           ('центробежный', re.compile(r'центробежн|турбо', re.I)),
           ('мембранный/адсорбционный', re.compile(r'мембранн|адсорбцион', re.I)))
CHUZH = re.compile(r'вентилятор|дымосос|\bнасос\w*\b|градирн|кондиционер|трактор|сельхоз|'
                   r'автотранспорт|стартер|автомат\w*\s+выключател|\bIP\d\d\b|\bВ\s*\d+А\b', re.I)
POMESH = re.compile(r'здани|укрыти|помещени|цех\b|корпус', re.I)
POZ = re.compile(r'поз\.?\s*$|№\s*$', re.I)

s_ = collections.defaultdict(lambda: {'v': 0, 'sem': '', 'p': collections.Counter(),
                                      'vid': collections.Counter(), 'inn': set(),
                                      'url': set(), 'cit': ''})
snyato = collections.Counter()
for baza, tabl in ISTOCHNIKI:
    if not os.path.exists(baza):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        kol = [r[1] for r in cx.execute('pragma table_info("%s")' % tabl)]
    except Exception:  # noqa: BLE001
        continue
    if not kol:
        cx.close(); continue
    pinn = 'inn' if 'inn' in kol else None
    for r in cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in kol), tabl)):
        d = dict(zip(kol, r))
        tekst = ' '.join(str(v) for v in r if v is not None)
        if len(tekst) < 8 or not re.search(r'компрессор|воздуходув|азот|кислород|пневмат|'
                                           r'осушител|ВРУ|МКС', tekst, re.I):
            continue
        for sem, rg in SEMEYSTVA:
            for m in rg.finditer(tekst):
                s = re.sub(r'\s+', '', m.group(0)).upper()
                do = tekst[max(0, m.start() - 60):m.start()]
                okno = tekst[max(0, m.start() - 130):m.end() + 130]
                if POZ.search(do):
                    snyato['позиция'] += 1; continue
                if CHUZH.search(okno):
                    snyato['чужая машина'] += 1; continue
                if POMESH.search(okno) and not re.search(r'компрессор|воздуходув', okno, re.I):
                    snyato['помещение'] += 1; continue
                z = s_[s]
                z['v'] += 1
                z['sem'] = z['sem'] or sem
                for i, rr in PRINCIP:
                    if rr.search(okno):
                        z['p'][i] += 1; break
                for i, rr in VID:
                    if rr.search(okno):
                        z['vid'][i] += 1; break
                if pinn and str(d.get(pinn) or '').strip():
                    z['inn'].add(str(d[pinn]).strip())
                for u in re.findall(r'https?://\S+', tekst)[:2]:
                    z['url'].add(u)
                if not z['cit']:
                    z['cit'] = re.sub(r'\s+', ' ', okno)[:150]
    cx.close()

itog = {s: z for s, z in s_.items() if z['v'] >= 2}
po_sem = collections.Counter(z['sem'] for z in itog.values())
po_vid = collections.Counter((z['vid'].most_common(1) or [('не установлен', 0)])[0][0]
                             for z in itog.values())

print('\n\n########## ПО ДЕСЯТЬ СЕРИЙ ИЗ КАЖДОГО СЕМЕЙСТВА, ГЛАЗАМИ')
for sem, _ in SEMEYSTVA:
    lst = sorted([(s, z) for s, z in itog.items() if z['sem'] == sem],
                 key=lambda x: -x[1]['v'])[:6]
    print('\n  === %s (серий %d)' % (sem, po_sem.get(sem, 0)))
    for s, z in lst:
        vd = (z['vid'].most_common(1) or [('?', 0)])[0][0]
        pr = (z['p'].most_common(1) or [('?', 0)])[0][0]
        print('    %-16s встреч %4d ИНН %3d ссылок %3d  %s / %s'
              % (s, z['v'], len(z['inn']), len(z['url']), pr, vd))
        print('       %s' % z['cit'][:120])

print('\n\n########## ЧИСЛА')
print('  серий найдено (встреч >= 2)  %5d' % len(itog))
for k, v in po_sem.most_common():
    print('     семейство %-34s %5d' % (k, v))
print('  --- по виду машины')
for k, v in po_vid.most_common():
    print('     %-34s %5d' % (k, v))
print('  --- снято заслонами')
for k, v in snyato.most_common():
    print('     %-34s %5d' % (k, v))
print('  разных ИНН по этим сериям    %5d'
      % len({i for z in itog.values() for i in z['inn']}))
print('ИТОГ ' + json.dumps({'серий': len(itog), 'семейства': dict(po_sem),
                            'виды': dict(po_vid)}, ensure_ascii=False))
