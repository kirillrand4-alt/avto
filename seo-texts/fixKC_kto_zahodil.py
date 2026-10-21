# -*- coding: utf-8 -*-
r"""fixKC (21.10): кто из менеджеров панели КЦ дольше всех не заходил – по журналу сервера (открытые карточки компаний:
ИНН в адресе -> чья компания по назначению). Только чтение; печатает формат строк журнала (без cookie/IP целиком)
и последние даты/строки по каждому менеджеру.

    python3 zapusk_na_servere.py fixKC_kto_zahodil.py
"""
import collections
import os
import re
import sqlite3
import time

LOGI = [r'C:\seostat\obzvon-service.log', r'C:\seostat\logs\out.log', r'C:\seostat\logs\err.log']
s = sqlite3.connect(r'file:C:\seostat\data\centro_sales.db?mode=ro', uri=True)
chya = dict(s.execute('SELECT inn, username FROM company_assignment'))
for p in LOGI:
    if not os.path.exists(p):
        continue
    t = open(p, encoding='utf-8', errors='replace').read()
    stroki = t.splitlines()
    karty = [(i, l) for i, l in enumerate(stroki) if re.search(r'GET /obzvon/centro\?[^" ]*inn=\d', l)]
    print('\n%s: строк %d, изменён %s, открытий карточек %d' % (p, len(stroki), time.strftime('%d.%m %H:%M', time.localtime(os.path.getmtime(p))), len(karty)))
    if karty:
        print('   пример строки:', re.sub(r'\d+\.\d+\.\d+\.\d+', 'IP', karty[-1][1])[:200])
    data_re = re.compile(r'(20\d\d-\d\d-\d\d[ T]\d\d:\d\d|\d\d/\w{3}/20\d\d:\d\d:\d\d|\d\d\.\d\d\.20\d\d \d\d:\d\d)')
    posl = {}
    sch = collections.Counter()
    for i, l in karty:
        m = re.search(r'inn=(\d{9,12})', l)
        u = chya.get(m.group(1)) if m else None
        if not u:
            continue
        sch[u] += 1
        d = data_re.search(l)
        if not d:                                       # ищем ближайшую строку выше с датой
            for j in range(i, max(-1, i - 200), -1):
                d = data_re.search(stroki[j])
                if d:
                    break
        posl[u] = (i, d.group(1) if d else 'дата в журнале не пишется')
    for u in sorted(set(chya.values())):
        print('   %s: открытий карточек своих компаний %d; последнее — строка %s, %s' % (
            u, sch.get(u, 0), posl.get(u, ('-',))[0], posl.get(u, ('', 'нет'))[1]))

# ---- якоря по времени и окружение последних открытий (только для obzvon-service.log)
t = open(LOGI[0], encoding='utf-8', errors='replace').read().splitlines()
print('\nякоря: старты сервера – строки', [i for i, l in enumerate(t) if 'Started server process' in l][-6:])
print('POST-действия (сохранение отметок и т.п.) – последние строки:',
      [(i, re.sub(r'\d+\.\d+\.\d+\.\d+:\d+', 'IP', l).split('"')[1][:60]) for i, l in enumerate(t) if '"POST /obzvon/centro' in l][-8:])
print('входы POST /login – последние строки:', [i for i, l in enumerate(t) if 'POST /obzvon/centro/login' in l][-8:])
print('\nпоследние 45 строк (IP скрыт, ИНН -> чей):')
for i in range(max(0, len(t) - 45), len(t)):
    l = re.sub(r'\d+\.\d+\.\d+\.\d+:\d+', 'IP', t[i])
    m = re.search(r'inn=(\d{9,12})', l)
    print('  %5d %s%s' % (i, l[:120], ('  <- ' + str(chya.get(m.group(1)))) if m else ''))
