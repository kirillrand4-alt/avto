# -*- coding: utf-8 -*-
"""Таблица `fact` — наше хранилище доказательств. Смотрю её колонки и источники ЦЕЛИКОМ.

Прошлый заход угадал колонку (`model`) и получил правдоподобные единицы вместо картины.
Угаданное имя поля даёт правдоподобный ноль — за это уже заплачено. Здесь сперва печатаю
схему, потом считаю по РЕАЛЬНЫМ колонкам.
"""
import collections
import json
import re
import sqlite3

MASH = re.compile(r'компрессор|нагнетател|турбокомпрессор|воздуходувк|газодувк|'
                  r'воздухоразделен|\bВРУ\b|азотн|кислородн|\bМКС\b|осушител', re.I)
OPO = re.compile(r'\bОПО\b|опасн\w+ производствен|ростехнадзор|регистрац\w+ опасн|'
                 r'свидетельств\w+ о регистрац', re.I)

cx = sqlite3.connect('file:C:/seostat/data/centrifugal.db?mode=ro', uri=True)
kol = [r[1] for r in cx.execute('pragma table_info(fact)')]
print('fact колонки: %s' % kol)
print('строк: %d' % cx.execute('select count(*) from fact').fetchone()[0])

print('\n=== ИСТОЧНИКИ ЦЕЛИКОМ (что вообще доказывает наши факты)')
for s, n in cx.execute('select source, count(*) from fact group by source order by 2 desc limit 30'):
    print('  %-52s %6d' % (str(s)[:52], n))

sel = ','.join('"%s"' % k for k in kol)
sch_m, sch_opo = collections.Counter(), collections.Counter()
primery = []
for r in cx.execute('select %s from fact' % sel):
    d = dict(zip(kol, r))
    vse = ' '.join(str(v or '') for v in r)
    s = str(d.get('source') or '(нет)')[:52]
    if MASH.search(vse):
        sch_m[s] += 1
        if len(primery) < 8:
            primery.append(d)
    if OPO.search(vse):
        sch_opo[s] += 1
cx.close()

print('\n=== ГДЕ УПОМЯНУТА НАША МАШИНА (по всей строке факта)')
for k, v in sch_m.most_common(20):
    print('  %-52s %6d' % (k, v))
print('  ВСЕГО фактов с машиной: %d' % sum(sch_m.values()))

print('\n=== ГДЕ УПОМЯНУТ ОПО / РОСТЕХНАДЗОР')
for k, v in sch_opo.most_common(20):
    print('  %-52s %6d' % (k, v))
print('  ВСЕГО фактов с ОПО/РТН: %d' % sum(sch_opo.values()))

print('\n=== ВОСЕМЬ ФАКТОВ С МАШИНОЙ ГЛАЗАМИ')
for d in primery:
    print('\n  %s' % json.dumps({k: (str(v)[:150] if v else '') for k, v in d.items() if v},
                                ensure_ascii=False)[:520])
print('\nИТОГ ' + json.dumps({'с машиной': sum(sch_m.values()),
                              'с ОПО/РТН': sum(sch_opo.values())}, ensure_ascii=False))
