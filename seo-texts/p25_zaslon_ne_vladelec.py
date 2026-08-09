# -*- coding: utf-8 -*-
"""ЗАСЛОН «не владелец»: продавец, сервис, подрядчик, НИИ — не наш клиент, а наш конкурент.

Глазами на редких типах машин видно, кого мы туда набрали:

    ВИНТКОМПЛЕКТ    «официальный дистрибьютор винтовых и безмасляных компрессоров»
    МАГЕРОН         «официальный дистрибьютор и авторизованный сервисный центр»
    ТЕХНОСЕРВИС     «сервисное обслуживание и ремонт компрессорного оборудования»
    ЛЕНГАЗСПЕЦСТРОЙ «строительство магистральных газопроводов и компрессорных станций»
    ЗАВОД МКС       ОКВЭД 25.11 металлоконструкции — МКС в НАЗВАНИИ, а не машина

Без заслона любой добор по редким типам наберёт продавцов, и число обрадует.

ВАЖНО: в `companies` уже есть колонка `is_competitor`. Сверяюсь с ней, а не завожу третью
линейку — иначе получим два разных ответа на один вопрос, как уже было трижды за смену.

Только чтение.
"""
import collections
import json
import re
import sqlite3

PRODAVEC = re.compile(
    r'дистрибьютор|дилер|торгов\w+\s+дом|поставк\w+\s+(?:компрессор|оборудован)|'
    r'официальн\w+\s+представител|сервисн\w+\s+центр|сервисн\w+\s+обслуживан|'
    r'продаж\w+\s+(?:компрессор|оборудован)|аренда\s+(?:компрессор|оборудован)|'
    r'ремонт\s+компрессорн|запчаст|комплектующ', re.I)
PODRYADCHIK = re.compile(r'строительств\w+\s+(?:магистральн|газопровод|компрессорн)|'
                         r'монтаж\w*\s+(?:оборудован|компрессорн)|пусконаладочн|'
                         r'проектирован\w+\s+(?:компрессорн|газопровод)', re.I)
NII = re.compile(r'\bНИИ\b|научно-исследовательск|конструкторск\w+\s+бюро|\bНИОКР\b|'
                 r'институт\b', re.I)
V_IMENI = re.compile(r'компрессор|\bМКС\b|пневмат|азот|кислород', re.I)
# ОКВЭД торговли и услуг — 46.x оптовая, 47.x розница, 77.x аренда, 33.x ремонт, 71-72 наука
OKVED_NE_VLADELEC = re.compile(r'^(46|47|77|33|71|72|70|82|62|63)\.', re.I)

cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
kol = [r[1] for r in cx.execute('pragma table_info(companies)')]
print('companies колонки: %s' % kol)
sel = ','.join('"%s"' % k for k in kol)

sch = collections.Counter()
primery = collections.defaultdict(list)
podozr = set()
konkurent_pole = set()
for r in cx.execute('select %s from companies' % sel):
    d = dict(zip(kol, r))
    inn = str(d.get('inn') or '').strip()
    if not inn:
        continue
    sch['всего компаний'] += 1
    nazv = str(d.get('name') or '') + ' ' + str(d.get('short_name') or '')
    act = str(d.get('activity') or '')
    okv = str(d.get('okved') or '')
    prichiny = []
    if str(d.get('is_competitor') or '0') not in ('0', '', 'None'):
        konkurent_pole.add(inn)
        prichiny.append('поле is_competitor')
    if PRODAVEC.search(act) or PRODAVEC.search(nazv):
        prichiny.append('продавец/сервис')
    if PODRYADCHIK.search(act):
        prichiny.append('подрядчик')
    if NII.search(act) or NII.search(nazv):
        prichiny.append('НИИ/КБ')
    if V_IMENI.search(nazv) and not V_IMENI.search(act):
        prichiny.append('машина в НАЗВАНИИ, а не в деятельности')
    if OKVED_NE_VLADELEC.match(okv):
        prichiny.append('ОКВЭД торговли/услуг: %s' % okv)
    if prichiny:
        podozr.add(inn)
        for p in prichiny:
            sch[p] += 1
            if len(primery[p]) < 3:
                primery[p].append('%s %s | ОКВЭД %s | %s'
                                  % (inn, nazv[:40], okv, act[:70]))
cx.close()

print('\n\n########## ПРИМЕРЫ ПО КАЖДОЙ ПРИЧИНЕ, ГЛАЗАМИ')
for p, lst in primery.items():
    print('\n  --- %s' % p)
    for x in lst:
        print('     %s' % x)

print('\n\n########## ЧИСЛА')
for k, v in sch.most_common():
    print('  %-46s %6d' % (k, v))
print('  РАЗНЫХ ИНН под подозрением «не владелец»       %6d' % len(podozr))
print('  из них помечены полем is_competitor            %6d' % len(konkurent_pole))
print('  подозрительных, которых поле НЕ знает          %6d'
      % len(podozr - konkurent_pole))
print('ИТОГ ' + json.dumps({'подозрительных': len(podozr),
                            'в поле is_competitor': len(konkurent_pole)},
                           ensure_ascii=False))
