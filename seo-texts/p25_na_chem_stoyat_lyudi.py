# -*- coding: utf-8 -*-
"""На каких страницах вообще стоят люди моего канала. Не выборка, а весь канал.

Владелец открыл ОДНУ карточку и нашёл на ней человека из дома культуры. Чтение всех 18
показало, что это не случайность: с сайта самого предприятия взяты трое, а остальные —
со страницы «наша гордость» химико-технологического института (список выпускников и где
они работают), из графика проверки знаний Ростехнадзора, из базы кандидатов на выборах и
с белорусского городского сайта.

На всех этих страницах человек НАЗВАН вместе с предприятием — поэтому мой разбор его и
взял. Но названность рядом это не работа там: институт хвалится выпускником, Ростехнадзор
перечисляет сдающих экзамен, выборы печатают место работы кандидата со слов кандидата.
Близость не доказывает принадлежность — то же правило, которым я весь день ловила номера,
и к людям я его не применила.

Прибор раскладывает ВЕСЬ канал по роду страницы-источника и печатает, сколько людей на
чём держится. Никакой выборки: вопрос в том, много ли таких, а не бывают ли они.
"""
import collections
import json
import re
import sqlite3
import urllib.parse

BAZA = 'file:C:/seostat/data/centrifugal.db?mode=ro'

ROD = (
    ('вуз, техникум, «наша гордость»', re.compile(r'\b(?:nchti|vuz|institut|akadem|univer|college|tehnikum|edu)\b|'
                r'\.edu\.|наша-гордость|выпускник|студент', re.I)),
    ('надзор: график экзаменов, реестры', re.compile(
        r'gosnadzor|rostehnadzor|rostechnadzor|nadzor|proverki-znaniy|attestac', re.I)),
    ('выборы: карточка кандидата', re.compile(r'vybory|izbirkom|kandidat', re.I)),
    ('справочник организаций или города', re.compile(
        r'citycode|orgpage|rusprofile|list-org|sbis|checko|zachestnyi|spravochnik|'
        r'katalog|2gis|yell\.ru|orgs\.', re.I)),
    ('соцсеть, новость, форум', re.compile(
        r'vk\.com|vk\.ru|ok\.ru|facebook|instagram|t\.me|telegram|dzen|livejournal|'
        r'forum|blog|news|novost', re.I)),
    ('госпортал, муниципалитет', re.compile(r'gosuslugi|gov\.ru|admin|municip|okrug', re.I)),
    ('карточка закупки', re.compile(
        r'zakupki\.gov|tender\.pro|etpgpb|roseltorg|tektorg|sberbank-ast|rts-tender', re.I)),
)

b = sqlite3.connect(BAZA, uri=True)
polya = [r[1] for r in b.execute('pragma table_info(person)')]
sayty = {i: (s or '').lower() for i, s in b.execute(
    'select inn, coalesce(sayt,"") from company')}


def domen(u):
    u = str(u or '').strip().lower()
    u = re.sub(r'^https?://', '', u).split('/')[0]
    return re.sub(r'^www\.', '', u)


sch = collections.Counter()
primery = collections.defaultdict(list)
for r in b.execute('select %s from person' % ','.join(polya)):
    z = dict(zip(polya, r))
    if 'поиск-ЛПР' not in str(z.get('source') or ''):
        continue
    url = urllib.parse.unquote(str(z.get('source_url') or ''))
    d = domen(url)
    svoy = sayty.get(str(z.get('inn') or ''), '')
    rod = ''
    # СВОЙ САЙТ ПРОВЕРЯЕТСЯ ПЕРВЫМ: порядок проверок есть правило, и заслон, стоящий
    # раньше разрешения, отменял бы разрешение молча.
    if d and svoy and (d in svoy or domen(svoy) in d):
        rod = 'САЙТ САМОГО ПРЕДПРИЯТИЯ'
    else:
        for imya, rg in ROD:
            if rg.search(url):
                rod = imya
                break
        if not rod:
            rod = 'прочее, род не опознан' if url else 'ссылки нет вовсе'
    sch[rod] += 1
    if len(primery[rod]) < 3:
        primery[rod].append((str(z.get('person') or '')[:26],
                             str(z.get('position') or '')[:24], d[:34]))

for rod, sp in sorted(primery.items(), key=lambda x: -sch[x[0]]):
    print('\n--- %s (%d)' % (rod, sch[rod]))
    for chel, pos, d in sp:
        print('    %-26s %-24s %s' % (chel, pos, d))
vsego = sum(sch.values())
print('ИТОГ ' + json.dumps({
    'людей канала': vsego,
    'на сайте самого предприятия': sch.get('САЙТ САМОГО ПРЕДПРИЯТИЯ', 0),
    'доля своих, %': round(100.0 * sch.get('САЙТ САМОГО ПРЕДПРИЯТИЯ', 0) / vsego, 1)
    if vsego else 0}, ensure_ascii=False))
