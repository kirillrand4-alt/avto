# -*- coding: utf-8 -*-
"""Из какого поля панель печатает должность: `post` или `position`.

Шаблон карточки печатает `{{ p.post }}`. Я весь день писала должности в `position`.
Если поля `post` в таблице нет или оно пустое, то на витрине у людей нет должностей —
при том что в базе они есть. Это ровно тот класс промаха, что и «панель не знает моих
колонок»: работа сделана, до глаз не доехала.

Прибор печатает: какие поля есть у person, сколько строк заполнено в каждом из двух, и
десяток примеров, где одно пусто, а другое нет. Ничего не пишет — сперва увидеть.
"""
import collections
import json
import sqlite3

BAZA = 'file:C:/seostat/data/centrifugal.db?mode=ro'
b = sqlite3.connect(BAZA, uri=True)
polya = [r[1] for r in b.execute('pragma table_info(person)')]
print('поля person: %s' % ', '.join(polya))

sch = collections.Counter()
sch['строк всего'] = b.execute('select count(*) from person').fetchone()[0]
for p in ('post', 'position', 'role'):
    if p in polya:
        sch['заполнено %s' % p] = b.execute(
            'select count(*) from person where coalesce(%s,"") <> ""' % p).fetchone()[0]
    else:
        sch['ПОЛЯ %s НЕТ ВОВСЕ' % p] = 1

if 'post' in polya and 'position' in polya:
    sch['position есть, post пусто'] = b.execute(
        'select count(*) from person where coalesce(position,"") <> "" '
        'and coalesce(post,"") = ""').fetchone()[0]
    sch['post есть, position пусто'] = b.execute(
        'select count(*) from person where coalesce(post,"") <> "" '
        'and coalesce(position,"") = ""').fetchone()[0]
    print('\n--- примеры, где должность есть в position, а в post пусто')
    for r in b.execute('select person, position, coalesce(post,""), coalesce(role,"") '
                       'from person where coalesce(position,"") <> "" '
                       'and coalesce(post,"") = "" limit 10'):
        print('    %-30s position=%-34s post=%-6s role=%s'
              % (r[0][:30], r[1][:34], r[2][:6] or '—', r[3][:18]))

# Как выглядит человек глазами шаблона: имя, p.post, телефон.
print('\n--- что увидит продавец на витрине (первые 10 технических)')
usl = 'where coalesce(role,"") <> ""' if 'role' in polya else ''
for r in b.execute('select person, %s, coalesce(role,""), coalesce(phone,"") from person %s '
                   'limit 10' % ('coalesce(post,"")' if 'post' in polya else '""', usl)):
    print('    %-30s значок=%-24s role=%-16s тел=%s'
          % (str(r[0])[:30], (r[1] or 'ПУСТО')[:24], r[2][:16], r[3][:16]))

for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'есть post': 'post' in polya,
                            'есть position': 'position' in polya}, ensure_ascii=False))
