# -*- coding: utf-8 -*-
"""Поправки B и C 1-й сессии — считаю на тех же 2 468 телефонах. Обе против МОЕЙ же меры.

Поправка C — это буквально моё собственное правило из P25 «номер у нескольких предприятий»,
которое я НЕ применила к своей новой мере. Свёртка по ИНН+номер верна внутри предприятия,
но номер колл-центра, засветившийся у пяти ИНН, даст пять «личных» контактов, и каждый
пройдёт проверку `imen=1`. Считаю `innov` — у скольких РАЗНЫХ ИНН встречается номер.

Поправка B — мера владельца это «технический ЛПР с ЛИЧНЫМ МОБИЛЬНЫМ», а мой флаг `lichnyy`
её не даёт: номер, встреченный один раз с одним именем, выглядит так же, как приёмная,
в которую попал один секретарь. Считаю отдельно формат +7 9xx.

Только чтение.
"""
import collections
import json
import re
import sqlite3

BAZA = r'C:\seostat\drop\drop-storage\atlas_copco.db'
URL = re.compile(r'https?://', re.I)
PERVOIST = re.compile(r'zakupki\.gov\.ru|tender\.pro|etpgpb|roseltorg|tektorg|rts-tender|'
                      r'sberbank-ast|b2b-center|fabrikant|gosnadzor|zakupki\.mos\.ru', re.I)
AGREGATOR = re.compile(r'checko|rusprofile|list-org|zachestnyi|sbis\.ru|audit-it|2gis|'
                       r'yell\.ru|orgpage|spark|kartoteka', re.I)


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
kol = [r[1] for r in cx.execute('pragma table_info(kontakty_svod)')]
sel = ','.join('"%s"' % k for k in kol)
pu = [k for k in kol if 'url' in k.lower() or 'ssyl' in k.lower() or k.lower() == 'source']
pt = [k for k in kol if 'phone' in k.lower() or 'tel' in k.lower()]

kont = collections.defaultdict(lambda: {'ssylki': set(), 'imena': set()})
nomer_inn = collections.defaultdict(set)
for r in cx.execute('select %s from kontakty_svod' % sel):
    d = dict(zip(kol, r))
    inn = str(d.get('inn') or '').strip()
    if not inn:
        continue
    ssyl = [str(d.get(k)).strip() for k in pu if d.get(k) and URL.search(str(d.get(k)))]
    imya = str(d.get('person') or '').strip()
    for k in pt:
        c = desyat(d.get(k))
        if not c:
            continue
        z = kont[(inn, c)]
        z['ssylki'].update(ssyl)
        if imya:
            z['imena'].add(imya)
        nomer_inn[c].add(inn)
cx.close()

sch = collections.Counter()
r_innov = collections.Counter()
primery = []
for (inn, c), z in kont.items():
    innov = len(nomer_inn[c])
    r_innov[min(innov, 6)] += 1
    perv = len([s for s in z['ssylki'] if PERVOIST.search(s)])
    agr = len([s for s in z['ssylki'] if AGREGATOR.search(s)])
    imen = len(z['imena'])
    lich_staryy = 1 if (imen == 1 and z['ssylki']) else 0
    lich_novyy = 1 if (imen == 1 and perv >= 1 and innov == 1) else 0
    mob = 1 if c.startswith('9') else 0
    sch['всего контактов'] += 1
    sch['ЛИЧНЫЙ по МОЕЙ мере (imen=1, ssylok>=1)'] += lich_staryy
    sch['ЛИЧНЫЙ по ПОПРАВЛЕННОЙ (imen=1, первоисточник>=1, innov=1)'] += lich_novyy
    sch['мобильный формат +7 9xx'] += mob
    sch['ЛИЧНЫЙ И МОБИЛЬНЫЙ (поправленная мера)'] += (lich_novyy and mob)
    if lich_staryy and not lich_novyy and len(primery) < 8:
        primery.append((inn, c, imen, innov, perv, agr, list(z['imena'])[:1]))

print('\n\n########## ПОПРАВКА C: у скольких РАЗНЫХ ИНН встречается номер')
for k in sorted(r_innov):
    print('   innov %-3s контактов %5d' % ('6+' if k == 6 else k, r_innov[k]))
print('   номеров, засветившихся более чем у одного ИНН: %d'
      % sum(1 for c, s in nomer_inn.items() if len(s) > 1))

print('\n########## ЧТО ОТСЕИВАЕТ ПОПРАВКА (было личным, стало нет) — глазами')
for inn, c, imen, innov, perv, agr, im in primery:
    print('   ИНН %-12s +7%s  имён %d  ИНН у номера %d  первоисточников %d  агрегаторов %d  %s'
          % (inn, c, imen, innov, perv, agr, im))

print('\n########## ЧИСЛА')
for k, v in sch.most_common():
    print('   %-58s %5d' % (k, v))
print('ИТОГ ' + json.dumps(dict(sch), ensure_ascii=False))
