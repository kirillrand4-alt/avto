# -*- coding: utf-8 -*-
"""Что панель умеет скрывать: виды `hidden_item` и то, как она их читает.

Пометки в базе панель не видит — проверено. Зато у неё есть СВОЙ рычаг: `hidden_item` в
`centro_sales.db`, откуда все её отборы вычитают скрытое. Значит отдать чистые данные —
это не завести четвёртую колонку, которой никто не читает, а нажать тот рычаг, которым
панель живёт уже сейчас.

Но нажимать вслепую нельзя: если панель умеет скрывать только предприятия, то скрыть
человека этим рычагом не выйдет, и попытка тихо ничего не сделает. Поэтому прибор сперва
смотрит, ЧТО там лежит: какие виды, сколько каждого, с какими причинами, — и отдельно
ищет в исходниках панели, какие виды она вообще читает.

Ничего не пишет.
"""
import collections
import io
import json
import os
import re

BAZY = (r'C:\seostat\data\centro_sales.db', r'C:\sender\centro_sales.db',
        r'C:\seostat\data\centrifugal.db')
KORNI = (r'C:\sender\server', r'C:\sender\web', r'C:\sender\panel', r'C:\sender')
MOYO = re.compile(r'[\\/](?:_ops)[\\/]|[\\/][123]s_', re.I)

import sqlite3

sch = collections.Counter()
print('=== что лежит в hidden_item')
nayden = False
for baza in BAZY:
    if not os.path.exists(baza):
        continue
    try:
        b = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in b.execute(
            "select name from sqlite_master where type='table' and name='hidden_item'")]
        if not tabl:
            b.close()
            continue
        nayden = True
        polya = [r[1] for r in b.execute('pragma table_info(hidden_item)')]
        print('\n%s   колонки: %s' % (baza, ', '.join(polya)))
        for kind, n in b.execute(
                'select kind, count(*) from hidden_item group by kind order by 2 desc'):
            print('    вид %-14s %6d' % (kind, n))
            sch['вид %s' % kind] += n
        print('    примеры причин:')
        for r in b.execute('select kind, value, substr(coalesce(reason,""),1,80) '
                           'from hidden_item limit 6'):
            print('      %-10s %-14s %s' % (r[0], str(r[1])[:14], r[2]))
        b.close()
    except Exception as e:  # noqa: BLE001
        print('  %s не прочиталась: %s' % (baza, str(e)[:60]))
if not nayden:
    print('  таблицы hidden_item не нашлось ни в одной из баз')

print('\n=== какие виды панель читает (её собственные исходники)')
vidy = collections.Counter()
gde = collections.defaultdict(set)
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if re.search(r'[\\/](?:node_modules|\.git|__pycache__)[\\/]', put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith(('.py', '.js', '.html', '.jsx', '.ts')):
                continue
            p = os.path.join(put, f)
            if MOYO.search(p):
                continue
            try:
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            for m in re.finditer(r"kind\s*(?:=|==|:)\s*['\"]([a-z_]+)['\"]", t):
                vidy[m.group(1)] += 1
                gde[m.group(1)].add(p[-52:])
for v, n in vidy.most_common(14):
    print('    %-14s упоминаний %-4d  %s' % (v, n, '; '.join(sorted(gde[v])[:2])))

for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'виды в базе': sorted(k[4:] for k in sch),
                            'виды в коде панели': sorted(vidy)}, ensure_ascii=False))
