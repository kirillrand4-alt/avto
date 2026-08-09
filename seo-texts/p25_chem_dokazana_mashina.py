# -*- coding: utf-8 -*-
"""ЧЕМ у нас доказано наличие машины — по источникам, числом. Не мнение, а замер.

Вопрос владельца: сосед ищет доказательства наличия компрессоров/генераторов азота и
кислорода и что-то делает не так. Прежде чем говорить «не так», смотрю, что уже есть:
какие источники в базах доказывают МАШИНУ (а не контакт), и сколько каждый дал.

Только чтение, все базы в mode=ro.
"""
import collections
import json
import os
import re
import sqlite3

BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db',
        r'C:\seostat\data\p25.db', r'C:\sender\tehlpr.db',
        r'C:\seostat\data\centro_sales.db']
MASH = re.compile(r'компрессор|нагнетател|турбокомпрессор|воздуходувк|газодувк|'
                  r'воздухоразделен|\bВРУ\b|азотн|кислородн|\bМКС\b|осушител', re.I)

for b in BAZY:
    if not os.path.exists(b):
        print('нет базы: %s' % b)
        continue
    cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
    tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    print('\n\n########## %s' % b)
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
            n = cx.execute('select count(*) from "%s"' % t).fetchone()[0]
        except Exception:  # noqa: BLE001
            continue
        if not n:
            continue
        # где вообще может лежать доказательство машины
        pol_ist = [k for k in kol if k.lower() in
                   ('source', 'istochnik', 'src', 'kind', 'vid', 'tip', 'type')]
        pol_tekst = [k for k in kol if k.lower() in
                     ('fact', 'text', 'what', 'opisanie', 'descr', 'note', 'marka',
                      'model', 'mashina', 'obj', 'object', 'name')]
        if not (pol_ist and pol_tekst):
            continue
        ist, tek = pol_ist[0], pol_tekst[0]
        sch = collections.Counter()
        try:
            for i, x in cx.execute('select "%s","%s" from "%s"' % (ist, tek, t)):
                if MASH.search(str(x or '')):
                    sch[str(i or '(без источника)')[:46]] += 1
        except Exception:  # noqa: BLE001
            continue
        if not sch:
            continue
        print('\n  --- %s (строк %d), источник=%s текст=%s' % (t, n, ist, tek))
        for k, v in sch.most_common(14):
            print('      %-48s %6d' % (k, v))
    cx.close()

print('\nИТОГ {"смотрела": "чем доказана машина по источникам"}')
