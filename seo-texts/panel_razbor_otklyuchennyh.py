# -*- coding: utf-8 -*-
"""Где панель перечисляет продавцов — чтобы убрать отключённых везде, а не местами.

Отключённые (is_active=0) — это user1..user3 и admin, унаследованные с боевой панели.
Владелец: «юзер отключен убери теперь». Из базы не удаляю: на них висят назначения,
состояния, комментарии и журнал, удаление необратимо. Убираю из показа.
"""
import io
import os
import re

KOREN = r'C:\centro2'
OTCHET = r'C:\seostat\drop\drop-storage\razbor-otkl.txt'
vyhod = []


def pishi(s=''):
    vyhod.append(str(s))


RCS = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
CS = os.path.join(KOREN, 'app', 'services', 'centro_sales.py')

for imya, put in (('routes_centro_sales.py', RCS), ('centro_sales.py', CS)):
    t = io.open(put, encoding='utf-8', errors='replace').read().splitlines()
    for i, l in enumerate(t, 1):
        if re.search(r'FROM users|from users|sales_users|def admin|centro_admin\.html|'
                     r'def assignment_stats|def .*stats\(|is_active', l):
            pishi()
            pishi('--- %s:%d' % (imya, i))
            for j in range(max(0, i - 4), min(len(t), i + 12)):
                pishi('   %4d: %s' % (j + 1, t[j].rstrip()[:170]))

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
