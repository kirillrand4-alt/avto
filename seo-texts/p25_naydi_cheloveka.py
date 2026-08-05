# -*- coding: utf-8 -*-
"""Найти человека и предприятие по фамилии/почте/домену во ВСЕХ наших базах.

Запуск: python3 p25_naydi_cheloveka.py <что искать> [ещё что]
Например: p25_naydi_cheloveka.py самсонов ekoniva эконива

Ищет по всем таблицам всех баз в текстовых колонках. Печатает строку целиком, чтобы
видеть провенанс: откуда взято и чем подтверждено. Ничего не меняет.

ВАЖНО ПРО ПОИСК ПО-РУССКИ: SQL LIKE и lower() кириллицу не знают (общий урок смены),
поэтому сравнение делаю в Python, а не в SQL.
"""
import collections
import json
import os
import re
import sys

import sqlite3

BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\p25.db',
        r'C:\seostat\data\centrifugal.db', r'C:\sender\tehlpr.db',
        r'C:\sender\sender.db', r'C:\seostat\data\centro_sales.db']
ISKAT = [a.lower() for a in sys.argv[1:]] or ['самсонов', 'ekoniva', 'эконива']
print('ищу: %s' % ', '.join(ISKAT))

sch = collections.Counter()
nashli = []
for baza in BAZY:
    if not os.path.exists(baza):
        print('  нет базы: %s' % baza)
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        tablicy = [r[0] for r in cx.execute(
            "select name from sqlite_master where type='table'")]
    except Exception as e:  # noqa: BLE001
        print('  %s не открылась: %s' % (baza, str(e)[:60]))
        continue
    for t in tablicy:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info(%s)' % t)]
            if not kol:
                continue
            stroki = cx.execute('select %s from %s' % (','.join(kol), t))
        except Exception:  # noqa: BLE001
            continue
        try:
            for r in stroki:
                sklejka = ' '.join(str(x or '') for x in r).lower()
                if not any(a in sklejka for a in ISKAT):
                    continue
                z = {k: v for k, v in zip(kol, r) if v not in (None, '', 0)}
                nashli.append((os.path.basename(baza), t, z))
                sch['%s.%s' % (os.path.basename(baza), t)] += 1
                if len(nashli) > 400:
                    break
        except Exception:  # noqa: BLE001
            continue
    cx.close()

print('\n=== найдено строк: %d' % len(nashli))
for baza, t, z in nashli[:60]:
    print('\n--- %s . %s' % (baza, t))
    for k, v in z.items():
        s = str(v)
        if len(s) > 150:
            s = s[:150] + '…'
        print('    %-22s %s' % (k, s))

print()
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'строк найдено': len(nashli),
                            'искали': ISKAT}, ensure_ascii=False))
