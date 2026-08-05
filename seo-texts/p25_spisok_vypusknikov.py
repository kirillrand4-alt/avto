# -*- coding: utf-8 -*-
"""Страницы-СПИСКИ, где у каждой строки свой работодатель. Сколько людей я так набрала.

ВЛАДЕЛЕЦ ПОКАЗАЛ СТРАНИЦУ, И ОНА ОБЪЯСНЯЕТ ВСЁ РАЗОМ. `nchti.ru/наша-гордость` — это
нумерованный список выпускников института:

    1. Анисимов Сергей Александрович — технический директор, главный инженер
                                        ОАО «Нижнекамск-техуглерод» (выпуск 1989)
    2. Ахмадишин Фаиз Фаикович       — директор Нижнекамского Дома народного творчества
    3. Бикмурзин Азат Шаукатович     — директор завода «Этилен» ОАО «Нижнекамскнефтехим»

Имя предприятия стоит в ОДНОМ пункте. Мой разбор нашёл его на странице и приписал
предприятию ВСЕХ, кого на ней встретил, а должность взял ту, что стояла ближе, — то есть
чужую: Ахмадишин получил «главный инженер» Анисимова.

ЭТО ТОТ ЖЕ БРАК, ЧТО Я ЧИНИЛА УТРОМ В КАРТОЧКАХ ПЛОЩАДКИ, где Нестеров носил должность
Савчука. Там я ввела «полосу человека» — от его имени до следующего имени — и починила.
Сюда то же правило не перенесла, хотя страница устроена так же: список, у каждой строки
своё.

ПРИЗНАК СПИСКА, а не рассуждение: на странице много людей и много РАЗНЫХ работодателей,
а имя нашего предприятия встречается в одной строке из многих. Тогда предприятию
принадлежит только тот, в чьей строке оно названо.

Прибор считает, сколько людей канала пришло с таких страниц и скольких из них надо
отвязать. Ничего не удаляет: печатает список к пересмотру.
"""
import collections
import json
import re
import sqlite3
import urllib.parse

BAZA = 'file:C:/seostat/data/centrifugal.db?mode=ro'
# Признаки страницы-списка людей с разными работодателями.
SPISOK_V_ADRESE = re.compile(
    r'наша-гордость|gordost|vypuskn|выпускник|alumni|nashi-lyudi|pochetn|veteran|'
    r'proverki-znaniy|grafik|kandidat|spisok|reestr', re.I)

b = sqlite3.connect(BAZA, uri=True)
polya = [r[1] for r in b.execute('pragma table_info(person)')]
imena = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}

# Сколько РАЗНЫХ предприятий канал набрал с одной и той же страницы, и сколько людей.
po_stranice = collections.defaultdict(lambda: {'lyudi': [], 'inn': set()})
for r in b.execute('select %s from person' % ','.join(polya)):
    z = dict(zip(polya, r))
    if 'поиск-ЛПР' not in str(z.get('source') or ''):
        continue
    url = urllib.parse.unquote(str(z.get('source_url') or ''))
    if not url:
        continue
    po_stranice[url]['lyudi'].append((str(z.get('person') or ''),
                                      str(z.get('position') or ''),
                                      str(z.get('inn') or '')))
    po_stranice[url]['inn'].add(str(z.get('inn') or ''))

sch = collections.Counter()
opasnye = []
for url, d in po_stranice.items():
    n_lyudey, n_inn = len(d['lyudi']), len(d['inn'])
    spisok_po_adresu = bool(SPISOK_V_ADRESE.search(url))
    # СТРАНИЦА-СПИСОК: с неё взято много людей. Если при этом они розданы РАЗНЫМ
    # предприятиям — это уже доказано самим фактом раздачи; если одному, но людей
    # много, а адрес говорит «выпускники» или «график» — тоже список.
    if n_lyudey >= 4 and (n_inn >= 2 or spisok_po_adresu):
        sch['страниц-списков'] += 1
        sch['людей с них'] += n_lyudey
        opasnye.append((url, n_lyudey, n_inn, d['lyudi'][:3]))
    else:
        sch['страниц обычных'] += 1
        sch['людей с них'] += 0

opasnye.sort(key=lambda x: -x[1])
for url, n_lyudey, n_inn, primery in opasnye[:10]:
    print('\n--- %d человек, %d предприятий: %s' % (n_lyudey, n_inn, url[:96]))
    for chel, pos, inn in primery:
        print('      %-30s %-26s %s' % (chel[:30], pos[:26], (imena.get(inn) or inn)[:24]))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'страниц-списков': len(opasnye),
    'ЛЮДЕЙ К ПЕРЕСМОТРУ': sum(x[1] for x in opasnye)}, ensure_ascii=False))
