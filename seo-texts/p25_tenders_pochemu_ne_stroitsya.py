# -*- coding: utf-8 -*-
"""Почему адрес не построился у 38 706 строк. Смотрю сами значения, а не свои допущения.

Сборщик отверг их с формулировкой «площадка не ЕИС либо номер не цифровой». Формулировка
моя, и она объединяет две разные причины — значит она бесполезна, пока не разделена.
Печатаю: какие вообще бывают значения `platform`, как выглядит `reg_number` у каждой, и
десяток пар живьём. Числа в КОНЦЕ.
"""
import collections
import re
import sqlite3

BAZA = r'C:\seostat\drop\drop-storage\atlas_copco.db'
cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
pl = collections.Counter()
form = collections.Counter()
primery = []
for p, n, t in cx.execute('select platform, reg_number, title from tenders'):
    pl[str(p)] += 1
    s = str(n or '')
    if not s:
        form['пусто'] += 1
    elif s.isdigit():
        form['только цифры, длина %d' % len(s)] += 1
    else:
        form['НЕ только цифры: %s' % re.sub(r'\d', '#', s)[:24]] += 1
        if len(primery) < 10:
            primery.append('%s | %s | %s' % (p, s[:40], str(t)[:60]))
cx.close()
print('########## ДЕСЯТЬ НЕЦИФРОВЫХ ЖИВЬЁМ')
for x in primery:
    print('  ' + x)
print('\n########## ЧИСЛА')
print('  --- значения platform')
for k, v in pl.most_common(12):
    print('     %-24s %7d' % (k[:24], v))
print('  --- форма reg_number')
for k, v in form.most_common(14):
    print('     %-44s %7d' % (k[:44], v))
print('ИТОГ {"площадок": %d}' % len(pl))
