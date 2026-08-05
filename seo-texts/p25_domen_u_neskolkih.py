# -*- coding: utf-8 -*-
"""Один домен у нескольких ИНН — и держатся ли на таком мои закрытия.

ПОЧЕМУ ПРОВЕРЯЮ. 2-я сессия отзывает 17 доменов, отданных ранее как собственные сайты
предприятий, и приводит случай, который бьёт прямо по моей мере: `sibur.ru` заявлен
сайтом ПЯТИ разных ИНН (СИБУРТЮМЕНЬГАЗ, НИЖНЕКАМСКНЕФТЕХИМ, ТОМСКНЕФТЕХИМ,
ЗАПСИБТРАНСГАЗ, СИБУР-ХИМПРОМ).

Мой заслон `stranica_podtverzhdaet` засчитывает страницу первым же условием «хост
совпадает с сайтом предприятия». Если сайт группы записан собственным сайтом завода, то
контакт с него подтверждается для КАЖДОГО из пяти — и подтверждение выглядит строгим,
потому что формально оно и есть строгое: хост совпал.

Это тот же класс, что «номер у нескольких людей»: величина, которая должна быть
уникальной, на деле общая, и общность не проверялась.

ЧТО СЧИТАЕТСЯ. Домены, отданные двум и более ИНН, и мои закрытия по ТЗ, у которых
подтверждающая ссылка ведёт на такой домен. Второе важнее: это прямая проверка меры.
"""
import collections
import csv
import glob
import json
import os
import re
import sqlite3

OPS = r'C:\sender\_ops'
D = r'C:\seostat\drop\drop-storage'
csv.field_size_limit(10 ** 8)
SAYTY_GLOB = os.path.join(OPS, '3s_p25_sayty*.csv')


def domen(u):
    u = str(u or '').strip().lower()
    u = re.sub(r'^https?://', '', u).split('/')[0].split('?')[0]
    return re.sub(r'^www\.', '', u)


# 1. Домены и ИНН, которым они отданы.
komu = collections.defaultdict(set)
ves_domena = {}
for p in sorted(glob.glob(SAYTY_GLOB)):
    for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
        inn, s = (r.get('inn') or '').strip(), domen(r.get('sayt'))
        if not (inn and s):
            continue
        v = (r.get('ves') or '').strip()
        komu[s].add(inn)
        if v.isdigit():
            ves_domena[s] = max(ves_domena.get(s, 0), int(v))

obshchie = {d: i for d, i in komu.items() if len(i) >= 2}

b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
imena = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}

print('=== ДОМЕНЫ, ОТДАННЫЕ ДВУМ И БОЛЕЕ ПРЕДПРИЯТИЯМ')
for d_, inns in sorted(obshchie.items(), key=lambda x: -len(x[1]))[:14]:
    print('  %-28s вес %s, предприятий %d: %s'
          % (d_, ves_domena.get(d_, '—'), len(inns),
             ', '.join((imena.get(i) or i)[:22] for i in list(inns)[:4])))

# 2. Держатся ли МОИ ЗАКРЫТИЯ на таких доменах.
KRUG12 = re.compile(
    r'главн\w+\s+(?:инженер|механик|энергетик|технолог|сварщик|метролог|конструктор)|'
    r'техническ\w+\s+директор|начальник\w*\s+(?:цеха|производств|участка|службы|'
    r'ремонт\w*|энерго\w*)|механик|энергетик|технолог|инженер|КИПиА|АСУ', re.I)
NE_NASH = re.compile(r'персонал|кадр|закупк|снабж|бухгалт|юрист|секретар|маркетинг|'
                     r'продаж|устойчив\w+\s+развити|реклам|пресс', re.I)
PRIEMKA = re.compile(
    r'страница на сайте предприятия|на сайте холдинга|карточка закупки самого предприятия|'
    r'документ раскрытия|официальн\w+ реестр|заказчик написал|реестр ЭПБ|'
    r'tender\.pro, карточка закупки|контактное лицо заказчика назван', re.I)
OTKAZ = re.compile(
    r'не первоисточник|не сайт предприятия|новостн\w+, выставочн\w+|социальн\w+ домен|'
    r'агрегатор|карточка ОРГАНИЗАЦИИ|мошенн|запрещ[её]н|не проходит', re.I)


def lichnyy(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


KOL_TEL = ('LICHNYY_MOBILNYY', 'telefon', 'znachenie', 'nomer', 'telefon_kak_napisan')
KOL_IST = ('pervoistochnik', 'ssylka', 'ssylki', 'chem_podtverzhdena',
           'ssylka_na_kartochku', 'osnovanie', 'chem_dokazana_rol')
sch = collections.Counter()
opasnye = []
for p in sorted(glob.glob(os.path.join(D, 'P25-*3S*.csv'))):
    try:
        rows = list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'))
    except Exception:  # noqa: BLE001
        continue
    for r in rows:
        inn = (r.get('inn') or '').strip()
        if inn not in imena:
            continue
        dolzh = ' '.join(str(r.get(k) or '') for k in ('dolzhnost', 'dolzhnost_v_tekste'))
        if not KRUG12.search(dolzh) or NE_NASH.search(dolzh):
            continue
        if not any(lichnyy(r.get(k)) for k in KOL_TEL):
            continue
        ist = ' '.join(str(r.get(k) or '') for k in KOL_IST)
        if OTKAZ.search(ist) or not (PRIEMKA.search(ist)
                                     or (r.get('pervoistochnik') or '').strip().lower() == 'да'):
            continue
        ssyl = next((str(r.get(x)) for x in ('ssylka', 'ssylki', 'ssylka_na_kartochku')
                     if str(r.get(x) or '').startswith('http')), '')
        d_ = domen(ssyl)
        if d_ and d_ in obshchie:
            sch['ЗАКРЫТИЕ НА ДОМЕНЕ, ОТДАННОМ НЕСКОЛЬКИМ'] += 1
            opasnye.append((inn, (imena.get(inn) or '')[:26],
                            (r.get('chelovek') or r.get('fio') or '')[:24], d_,
                            len(obshchie[d_])))
        else:
            sch['закрытие на своём домене или на карточке'] += 1

print('\n=== ЗАКРЫТИЯ, ОПИРАЮЩИЕСЯ НА ОБЩИЙ ДОМЕН')
for inn, nazv, kto, d_, n in opasnye[:12]:
    print('  %-12s %-26s %-24s %s (у %d предприятий)' % (inn, nazv, kto, d_, n))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'доменов всего': len(komu), 'ОТДАНЫ ДВУМ И БОЛЕЕ': len(obshchie),
    'закрытий на общем домене': len(opasnye)}, ensure_ascii=False))
