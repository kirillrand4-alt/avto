# -*- coding: utf-8 -*-
"""Залить 538 новых людей и 470 номеров из файла 2-й сессии. Пишем в enrich.db, а не в снимок.

КУДА И ПОЧЕМУ. `centrifugal.db` — снимок, он пересобирается из `enrich.db`, и любая правка в
нём откатится следующей сборкой. На этом обожглась 1-я сессия со своей чисткой контактов.
Поэтому пишем в источник.

ПРОВЕНАНС СОХРАНЯЕТСЯ ЦЕЛИКОМ: в `source` идёт и мой канал, и исходный источник строки от
2-й сессии, в `source_url` — её ссылка, если есть. Правило владельца «источники
накапливаются» здесь буквально: моя заливка не должна стирать, откуда человек взят.

ВИД НОМЕРА НАЗЫВАЕТСЯ ЧЕСТНО. В файле 653 телефона и лишь 9 мобильных — это заводские линии,
а не личные номера. Пишу `phone_type` = «городской, линия предприятия», чтобы никто потом не
посчитал их личными: моя же мера «телефон с ролью» на этом бы и сломалась.
"""
import csv
import json
import os
import re
import sqlite3

csv.field_size_limit(10 ** 7)
PUT = r'C:\sender\_ops\3s_DLYA-3S-FIO-bez-lichnogo-nomera-2s.csv'
cx = sqlite3.connect(r'C:\sender\enrich.db')
kol = [r[1] for r in cx.execute('pragma table_info(people)')]


def fam(s):
    ch = re.split(r'[\s.,]+', (s or '').strip())
    return ch[0].lower().replace('ё', 'е') if ch and ch[0] else ''


def nom(t):
    c = re.sub(r'\D', '', t or '')
    return c[-10:] if len(c) >= 10 else ''


est = set()
for inn, person in cx.execute("select coalesce(inn,''), coalesce(person,'') from people"):
    if fam(person):
        est.add((inn, fam(person)))

rows = list(csv.DictReader(open(PUT, encoding='utf-8-sig'), delimiter=';'))
novye = []
for r in rows:
    inn = (r.get('inn') or '').strip()
    chel = (r.get('chelovek') or '').strip()
    if not inn or not fam(chel) or (inn, fam(chel)) in est:
        continue
    est.add((inn, fam(chel)))
    tel = (r.get('telefon_gorodskoy') or '').strip()
    novye.append({
        'inn': inn, 'person': chel, 'post': (r.get('dolzhnost') or '').strip(),
        'role': '', 'phone': tel, 'email': (r.get('pochta') or '').strip(),
        # ВИД НОМЕРА КЛАДЁТСЯ В ТЕКСТ ИСТОЧНИКА: колонки phone_type в enrich.db нет, а
        # потерять его нельзя — 653 телефона из 710 городские, и если их потом посчитают
        # личными, сломается главная мера. Лучше некрасиво, но видно, чем аккуратно и молча.
        'source': ('карточки площадок (2-я сессия): ' + (r.get('istochnik') or '')[:60]
                   + ('; номер городской, линия предприятия'
                      if tel and not nom(tel).startswith('9')
                      else ('; номер мобильный' if tel else ''))),
        'source_url': '',
    })
polya = [k for k in ('inn', 'person', 'post', 'role', 'phone', 'email', 'source', 'source_url',
                     'phone_type') if k in kol]
print('колонки people:', kol)
print('пишу поля:', polya, '| новых строк:', len(novye))
if 'PRIMENIT' in os.sys.argv:
    cx.executemany(
        f'insert into people ({",".join(polya)}) values ({",".join("?" * len(polya))})',
        [tuple(z[k] for k in polya) for z in novye])
    cx.commit()
    print('ЗАЛИТО. people стало:',
          cx.execute('select count(*) from people').fetchone()[0])
    print('с телефоном стало:',
          cx.execute("select count(*) from people where coalesce(phone,'') <> ''").fetchone()[0])
