# -*- coding: utf-8 -*-
"""fixK (локально): сводка для отчёта по заливке MEYER-7 – из otbor.json и plan.json.

    python3 -I fixK_otchet.py <папка fixK> <plan.json> > fixK-otchet-1310.txt
"""
import collections
import json
import os
import re
import sys

W, PLAN = sys.argv[1], sys.argv[2]
o = json.load(open(os.path.join(W, 'otbor.json'), encoding='utf-8'))
p = json.load(open(PLAN, encoding='utf-8'))
K = o['kandidaty']
FIO = p['fio']
PR = list(FIO)


def grp(prich):
    t = prich
    if t.startswith('выручка'):
        return 'выручка известна и меньше 30 млн'
    if t.startswith('активная сделка Meyer'):
        return 'активная сделка Meyer у самой компании'
    if t.startswith('возможна активная сделка'):
        return 'активная сделка Meyer по точному названию (тёзка не исключён)'
    if t.startswith('сегмент только по доп.'):
        return 'сегмент только по доп. ОКВЭД, основной нецелевой'
    if t.startswith('лес/химия'):
        return 'лес / химия'
    if t.startswith(('уже в панели', 'убрана из панели', 'в архиве')):
        return 'уже в панели или в архиве панели'
    if t.startswith('статус не проверен'):
        return 'статус не проверен (DaData не запрашивалась – дальше нужной части очереди)'
    if t.startswith('недействующая'):
        return 'недействующая (ЕГРЮЛ / checko / МНС РБ)'
    if t.startswith('список «Meyer'):
        return 'список «Meyer – не покупатель»' + (' (оценщик L: не покупатель)' if 'оценщик L: не покупатель' in t else
                                                   ' (оценщик L: неясно, не понадобилось)' if 'неясно' in t else
                                                   ' (оценки L нет)')
    if 'группе' in t or 'холдинг' in t:
        return 'конфликт «холдинг – домашний регион»'
    return t[:60]


print('=== ПРОВЕРКИ ПУЛА (fixK_otbor, весь пул %d + возвращённые) ===' % (len(K) + len(o['otkaz'])))
c = collections.Counter(grp(v[0]) for v in o['otkaz'].values())
for kk, n in c.most_common():
    print('  %-70s %5d' % (kk, n))
print('\n=== ПРОВЕРКИ ПРИ ОТБОРЕ (по очереди, до 1080) ===')
c = collections.Counter(grp(v[0]) for v in p['otkaz_otbora'].values())
for kk, n in c.most_common():
    print('  %-70s %5d' % (kk, n))
print('\n=== ВЗЯТО ===')
print(json.dumps(p['svod'], ensure_ascii=False, indent=1))
st = collections.Counter((K[i]['eda'], p['stupeni'][i]['tier']) for i in p['prodavcy'])
print('\nпо ступеням и отраслям (пищевка/агро | прочие):')
for t, n in ((4, '800 ЛПР с ФИО и мобильным'), (3, '600 ЛПР с мобильным'), (2, '400 ЛПР с рабочим'), (1, '200 без ЛПР')):
    print('  %-30s пищевка %4d   прочие %4d' % (n, st[(True, t)], st[(False, t)]))
seg = collections.Counter(re.sub(r'\s*\((?:[^()]*)\)\s*$', '', (next(c_ for c_ in p['kompanii'] if c_['inn'] == i).get('segment_meyer7') or ''))
                          for i in p['prodavcy'])
print('\nсегменты сборки (взятые):')
for kk, n in seg.most_common(40):
    print('  %-60s %4d' % (kk, n))
print('\n=== ТАБЛИЦА ПО ПРОДАВЦАМ (новые 120) ===')
print(p['tablica'])
print('\nконфликты групп: %s' % p['konflikty'])
print('групп (2+ компаний) с новыми: %d' % len({h['gruppa'] for h in p['holding_chlen']}))
