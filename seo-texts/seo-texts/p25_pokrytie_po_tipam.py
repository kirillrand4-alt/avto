# -*- coding: utf-8 -*-
"""ЧЕМ МЫ ПЕРЕКОШЕНЫ: сколько у нас фактов по КАЖДОМУ типу машины. По всем базам сразу.

Владелец поймал меня на прямом: словарь собран по `centrifugal.db` и по прогону Atlas Copco,
то есть по данным, накопленным ПОД ЦЕНТРОБЕЖКУ. Отсюда и вышло «центробежный 549, винтовой
45, поршневой 4, МКС 1, ВРУ 1». Это не редкость машин в стране — это наш охват.

Задача шире: ВСЕ компрессоры + МКС + генераторы азота и кислорода. Значит первым делом надо
увидеть дыру числом, а не на словах: по каждому типу — сколько строк и сколько РАЗНЫХ ИНН
у нас есть сегодня. Где мало — там и работа.

Считаю по ВСЕМ доступным базам, по каждому типу отдельным шаблоном с границами слова.
Только чтение.
"""
import collections
import json
import os
import re
import sqlite3

BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db',
        r'C:\seostat\drop\drop-storage\atlas_copco.db', r'C:\seostat\data\p25.db',
        r'C:\sender\tehlpr.db']

TIPY = (
    ('центробежный компрессор', re.compile(r'центробежн\w*\s+(?:компрессор|нагнетател|машин)|'
                                           r'турбокомпрессор', re.I)),
    ('ВИНТОВОЙ компрессор', re.compile(r'винтов\w*\s+компрессор|винтов\w*\s+блок|'
                                       r'компрессор\w*\s+винтов', re.I)),
    ('ПОРШНЕВОЙ компрессор', re.compile(r'поршнев\w*\s+компрессор|компрессор\w*\s+поршнев', re.I)),
    ('СПИРАЛЬНЫЙ/безмасляный', re.compile(r'спиральн\w*\s+компрессор|безмаслян\w*\s+компрессор', re.I)),
    ('МКС / передвижная станция', re.compile(r'\bМКС\b|передвижн\w*\s+компрессорн\w*|'
                                             r'мобильн\w*\s+компрессорн\w*|дизельн\w*\s+компрессор', re.I)),
    ('ГЕНЕРАТОР АЗОТА', re.compile(r'генератор\w*\s+азота|азотн\w*\s+станци|'
                                   r'мембранн\w*\s+азот|адсорбцион\w*\s+азот|'
                                   r'установк\w*\s+получени\w*\s+азота', re.I)),
    ('ГЕНЕРАТОР КИСЛОРОДА', re.compile(r'генератор\w*\s+кислорода|кислородн\w*\s+станци|'
                                       r'концентратор\w*\s+кислорода|'
                                       r'установк\w*\s+получени\w*\s+кислорода', re.I)),
    ('ВРУ / воздухоразделение', re.compile(r'воздухоразделительн|воздухоразделен|\bВРУ\b', re.I)),
    ('воздуходувка / газодувка', re.compile(r'воздуходув|газодув|турбовоздуходув', re.I)),
    ('осушитель воздуха', re.compile(r'осушител\w*\s+(?:сжат|возду)', re.I)),
    ('компрессорная станция', re.compile(r'компрессорн\w*\s+станци|компрессорн\w*\s+установк|'
                                         r'компрессорн\w*\s+хозяйств|компрессорн\w*\s+цех', re.I)),
    ('компрессор без типа', re.compile(r'\bкомпрессор\w*', re.I)),
)

svod = collections.defaultdict(lambda: {'strok': 0, 'inn': set(), 'primer': ''})
prosmotr = collections.Counter()

for baza in BAZY:
    if not os.path.exists(baza):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    except Exception:  # noqa: BLE001
        continue
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
            if not kol or 'inn' not in [k.lower() for k in kol]:
                continue
            pinn = [k for k in kol if k.lower() == 'inn'][0]
            n = cx.execute('select count(*) from "%s"' % t).fetchone()[0]
            if not n or n > 200000:
                continue
            rows = cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in kol), t))
        except Exception:  # noqa: BLE001
            continue
        for r in rows:
            d = dict(zip(kol, r))
            tekst = ' '.join(str(v) for v in r if v is not None)
            if len(tekst) < 8:
                continue
            prosmotr['%s.%s' % (os.path.basename(baza), t)] += 1
            inn = str(d.get(pinn) or '').strip()
            for imya, rg in TIPY:
                if rg.search(tekst):
                    z = svod[imya]
                    z['strok'] += 1
                    if inn:
                        z['inn'].add(inn)
                    if not z['primer']:
                        z['primer'] = re.sub(r'\s+', ' ', tekst)[:150]
                    break
    cx.close()

print('\n\n########## ПОКРЫТИЕ ПО ТИПАМ МАШИН — ЧТО У НАС ЕСТЬ СЕГОДНЯ')
print('  %-32s %8s %8s' % ('тип', 'строк', 'ИНН'))
for imya, _ in TIPY:
    z = svod.get(imya) or {'strok': 0, 'inn': set(), 'primer': ''}
    print('  %-32s %8d %8d' % (imya, z['strok'], len(z['inn'])))

print('\n  --- по одному примеру, глазами')
for imya, _ in TIPY:
    z = svod.get(imya)
    if z and z['primer']:
        print('\n  %s' % imya)
        print('     %s' % z['primer'][:140])

print('\n  --- просмотрено')
for k, v in prosmotr.most_common(10):
    print('     %-40s %7d' % (k, v))

print('ИТОГ ' + json.dumps({k: {'строк': v['strok'], 'ИНН': len(v['inn'])}
                            for k, v in svod.items()}, ensure_ascii=False))
