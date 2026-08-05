# -*- coding: utf-8 -*-
"""Пометить 525 человек, взятых со страниц-списков. Пометить, не удалить.

ЧТО ПОКАЗАЛ ВЛАДЕЛЕЦ И ЧТО ЗА ЭТИМ НАШЛОСЬ. Он открыл `nchti.ru/наша-гордость` —
нумерованный список выпускников института, где у КАЖДОЙ строки свой работодатель:

    1. Анисимов — главный инженер ОАО «Нижнекамск-техуглерод»
    2. Ахмадишин — директор Нижнекамского Дома народного творчества
    3. Бикмурзин — директор завода «Этилен» ОАО «Нижнекамскнефтехим»

Имя нужного предприятия стоит в ОДНОМ пункте, а мой разбор приписал предприятию всех,
кого встретил на странице, и раздал им должность ближайшего — Ахмадишин получил
«главный инженер» Анисимова.

СЧЁТ ПОКАЗАЛ, ЧТО ЭТО НЕ ПРО ВЫПУСКНИКОВ, А ШИРЕ. 54 страницы, 525 человек, и среди
них такие:

    kem-azot.ru/about/management/      руководство Кемеровского Азота -> АО «АММОНИЙ»
    kirovets-ptz.com/.../glavnogo-inzhenera  служба главного инженера Кировца ->
                                       «ТрансАвто (ТопПром)»
    volgaenergo.ru/Spisok_nevostrebovannykh_i_nelikvidnykh_TMTS  список НЕЛИКВИДОВ ->
                                       люди как штат ООО «СФМЗ»
    vk39.ru/Телефонный справочник.pdf  один справочник роздан семи предприятиям

То есть люди с одной страницы раздавались тому предприятию, КОТОРОЕ Я ИСКАЛА, а не
тому, чья это страница. Кировец — настоящий завод с настоящей службой главного
инженера, и его людей я приписала чужой фирме.

ПОЧЕМУ ПОМЕТКА, А НЕ УДАЛЕНИЕ. Люди настоящие и должности настоящие — неверна ПРИВЯЗКА
к предприятию. Половина этих страниц ещё и полезна: со списка выпускников видно, кто
где работает НА САМОМ ДЕЛЕ, и это вход для другого канала. Выброшенное заново не
добывается.

Без --apply ничего не пишется.
"""
import collections
import json
import re
import sqlite3
import sys
import urllib.parse

PUT = r'C:\seostat\data\centrifugal.db'
APPLY = '--apply' in sys.argv
SPISOK_V_ADRESE = re.compile(
    r'наша-гордость|gordost|vypuskn|выпускник|alumni|nashi-lyudi|pochetn|veteran|'
    r'proverki-znaniy|grafik|kandidat|spisok|список|reestr|spravochnik|справочник', re.I)

b = sqlite3.connect(PUT)
polya = [r[1] for r in b.execute('pragma table_info(person)')]
if 'privyazka_somnitelna' not in polya:
    if APPLY:
        b.execute('alter table person add column privyazka_somnitelna text')
        b.commit()
        polya.append('privyazka_somnitelna')
        print('колонка privyazka_somnitelna создана')
    else:
        print('колонки privyazka_somnitelna нет, будет создана')

po_stranice = collections.defaultdict(lambda: {'ids': [], 'inn': set()})
for r in b.execute('select id, inn, source, source_url from person'):
    pid, inn, ist, url = r
    if 'поиск-ЛПР' not in str(ist or ''):
        continue
    u = urllib.parse.unquote(str(url or ''))
    if not u:
        continue
    po_stranice[u]['ids'].append(pid)
    po_stranice[u]['inn'].add(str(inn or ''))

pometit = []
sch = collections.Counter()
for url, d in po_stranice.items():
    n_lyudey, n_inn = len(d['ids']), len(d['inn'])
    if n_lyudey >= 4 and (n_inn >= 2 or SPISOK_V_ADRESE.search(url)):
        prichina = ('страница-список: с неё взято %d человек%s — принадлежность '
                    'предприятию не доказана, у каждой строки свой работодатель'
                    % (n_lyudey,
                       (' и роздано %d предприятиям' % n_inn) if n_inn >= 2 else ''))
        for pid in d['ids']:
            pometit.append((prichina, pid))
        sch['страниц-списков'] += 1

if APPLY and pometit and 'privyazka_somnitelna' in polya:
    b.executemany('update person set privyazka_somnitelna = ? where id = ?', pometit)
    b.commit()
    sch['ПОМЕЧЕНО ЧЕЛОВЕК'] = len(pometit)
else:
    sch['БУДЕТ ПОМЕЧЕНО (сухой прогон)'] = len(pometit)

for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'режим': 'запись' if APPLY else 'сухой прогон',
                            'человек': len(pometit)}, ensure_ascii=False))
