# -*- coding: utf-8 -*-
"""Как устроены фильтры очереди: FILTER_ALIASES, _matches, _choice_values, диалог.

Нужно перед тем, как делать фильтры под Meyer (техЛПР, выручка, сегмент, ЛПР мобильный,
ОКВЭД по основному и доп.): какие параметры уже понимает сервер и как именно сравнивает,
чтобы новые фильтры легли в тот же механизм, а не рядом с ним. И как «Вся очередь»
отделяет обработанные — от этого зависят ссылки на карточки со страницы статистики.
"""
import io
import os
import re

KOREN = r'C:\centro2'
OTCHET = r'C:\seostat\drop\drop-storage\razbor-filtrov.txt'
vyhod = []
RCS = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
t = io.open(RCS, encoding='utf-8').read().splitlines()


def blok(nachalo, maks=140):
    for i, l in enumerate(t):
        if l.startswith(nachalo):
            vyhod.append('--- %s (строка %d)' % (nachalo, i + 1))
            for j in range(i, min(len(t), i + maks)):
                if j > i and (t[j].startswith('def ') or t[j].startswith('@router') or
                              (t[j] and not t[j][0].isspace() and not t[j].startswith(('#', ')', ']', '}')))):
                    break
                vyhod.append('   %4d: %s' % (j + 1, t[j].rstrip()[:180]))
            return


for n in ('FILTER_ALIASES', 'def _choice_values', 'def _matches', 'def _filter_value', 'def _num',
          'def _okved', 'def _text_value', 'def _bool'):
    blok(n)
# все обращения к query_params в маршрутах продаж
vyhod.append('')
vyhod.append('--- request.query_params в routes_centro_sales.py')
for i, l in enumerate(t, 1):
    if 'query_params' in l:
        vyhod.append('   %4d: %s' % (i, l.strip()[:170]))
# диалог «Все фильтры» целиком
C = os.path.join(KOREN, 'app', 'templates', 'centro.html')
ct = io.open(C, encoding='utf-8').read()
m = re.search(r'<dialog id="allFilters">.*?</dialog>', ct, re.S)
vyhod.append('')
vyhod.append('--- диалог «Все фильтры» (%d знаков)' % len(m.group(0)))
vyhod.append(m.group(0))
io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
