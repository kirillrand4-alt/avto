# -*- coding: utf-8 -*-
"""Случайная выборка новостных сигналов — чтобы разметить их ГЛАЗАМИ и завести меру.

Стадия A моя, и меры «подходящая новость» не существует вовсе. Построить её из головы
нельзя: порог, придуманный без разметки, будет мнением. Поэтому сперва размеченный
набор, и размечает его человек-читатель, а не счётчик.

ВЫБОРКА СЛУЧАЙНАЯ, И ЭТО НЕ ПРИДИРКА. Первые строки таблицы всегда самые заполненные
(их добирали руками, на них смотрели), и по ним лента выглядит лучше, чем есть. Беру по
случайным rowid из ВСЕЙ таблицы.

Печатаю по каждому сигналу всё, на чём его можно судить: предприятие, тип события,
текст `what` целиком, ссылку, накал, дату. Ничего не решаю за читателя — показываю.

Запуск: python3 p25_novosti_vyborka.py [--skolko N] [--zerno N]
"""
import collections
import json
import random
import re
import sqlite3
import sys

ENRICH = r'C:\sender\enrich.db'


def dovod(s, po_umolchaniyu):
    return int(sys.argv[sys.argv.index(s) + 1]) if s in sys.argv else po_umolchaniyu


SKOLKO = dovod('--skolko', 30)
ZERNO = dovod('--zerno', 20260805)

random.seed(ZERNO)
cx = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
imena = {str(i): (n or '') for i, n in cx.execute('select inn, name from companies')}
polya = [r[1] for r in cx.execute('pragma table_info(signals)')]
print('колонки signals: %s' % ', '.join(polya))

vse = list(cx.execute('select rowid, %s from signals' % ','.join(polya)))
print('сигналов всего: %d, беру случайных %d (зерно %d)' % (len(vse), SKOLKO, ZERNO))
vyborka = random.sample(vse, min(SKOLKO, len(vse)))

sch = collections.Counter()
for n, r in enumerate(vyborka, 1):
    z = dict(zip(['rowid'] + polya, r))
    inn = str(z.get('inn') or '')
    what = str(z.get('what') or '')
    url = str(z.get('source_url') or '')
    print('\n--- %02d  rowid %s  ИНН %s  %s' % (n, z['rowid'], inn,
                                                imena.get(inn, '(нет в companies)')[:44]))
    print('    тип: %-26s накал: %-3s источник: %s'
          % (str(z.get('event_type') or '')[:26], z.get('hotness'),
             str(z.get('source') or '')[:18]))
    print('    что: %s' % (what[:400] if what else '(пусто)'))
    print('    ссылка: %s' % (url[:110] or '(нет)'))
    if z.get('sum'):
        print('    сумма: %s' % z['sum'])
    sch['длина what < 60'] += 1 if len(what) < 60 else 0
    sch['ссылки нет или не http'] += 0 if url.startswith('http') else 1
    sch['имени компании НЕТ в тексте what'] += (
        0 if any(w.lower() in what.lower()
                 for w in re.findall(r'[А-ЯЁ][А-Яа-яЁё\-]{3,}',
                                     imena.get(inn, '')) [:3])
        else 1)

cx.close()
print()
for k, v in sch.most_common():
    print('REC %s\t%d из %d' % (k, v, len(vyborka)))
print('ИТОГ ' + json.dumps({'показано': len(vyborka), 'зерно': ZERNO},
                           ensure_ascii=False))
