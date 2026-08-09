# -*- coding: utf-8 -*-
"""Цели для поиска ЛПР по ОСТАЛЬНОМУ парку. Список для звонка закрыл 65 предприятий из 1 185.

Замер, из которого это следует:

    парк по трём потокам        1 185 различных ИНН
    список для звонка              65 предприятий (303 строки)
    ------------------------------------------------------------
    разрыв                      1 120 предприятий, где машина доказана, а звонить некому

Первый поиск ЛПР я гнала по 327 предприятиям — тем, что были в потоке 3 (реестр ЭПБ). Потоки
3b (закупки ЕИС) и 3c (ЭТП ГПБ) добавили 568 и 336 ИНН, и по ним поиск не ходил НИ РАЗУ.
Это и есть очередь.

Название предприятия обязательно: замер прошлой смены дал 10 доказуемых из 12 у полного
имени против 3 у аббревиатуры. Кому имени не нашлось — идут отдельной, слабой очередью и
считаются отдельно, а не молча теряются.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

POTOKI = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
          r'C:\sender\_ops\park_ingest_3c.jsonl']
UZHE = r'C:\sender\_ops\CELI-PARK-3S.csv'          # по кому поиск уже ходил
VYHOD = r'C:\sender\_ops\CELI-PARK-OSTALNOY-3S.csv'
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db',
        r'C:\seostat\drop\drop-storage\atlas_copco.db']
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}

park = {}
for p in POTOKI:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        i = o.get('inn')
        if not i:
            continue
        v = o.get('vid') or 'машина'
        if i not in park or KLASS.get(v, 0) > KLASS.get(park[i], 0):
            park[i] = v

uzhe = set()
if os.path.exists(UZHE):
    for s in io.open(UZHE, encoding='utf-8-sig').read().splitlines()[1:]:
        p_ = s.split(';')
        if p_ and p_[0].strip().isdigit():
            uzhe.add(p_[0].strip())

imena, sayty = {}, {}
for b in BAZY:
    if not os.path.exists(b):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    except Exception:  # noqa: BLE001
        continue
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        if 'inn' not in kol:
            continue
        pn = next((k for k in ('name', 'naimenovanie', 'company', 'predpriyatie') if k in kol), None)
        if not pn:
            continue
        ps = next((k for k in ('site', 'domain', 'sayt') if k in kol), None)
        q = 'select inn, "%s"%s from "%s"' % (pn, (', "%s"' % ps) if ps else '', t)
        try:
            for r in cx.execute(q):
                i = str(r[0] or '').strip()
                if i and r[1] and i not in imena:
                    imena[i] = re.sub(r'\s+', ' ', str(r[1])).strip()
                if ps and len(r) > 2 and r[2] and i not in sayty:
                    sayty[i] = str(r[2]).strip()
        except Exception:  # noqa: BLE001
            continue
    cx.close()

celi, bez_imeni = [], 0
for inn, vid in park.items():
    if inn in uzhe:
        continue
    nm = imena.get(inn, '')
    if not nm:
        bez_imeni += 1
    celi.append({'inn': inn, 'predpriyatie': nm, 'sayt': sayty.get(inn, ''),
                 'mashina': vid, 'klass': KLASS.get(vid, 2)})
celi.sort(key=lambda o: (-o['klass'], 0 if o['predpriyatie'] else 1))
with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie;sayt;mashina;klass\n')
    for o in celi:
        f.write(';'.join(str(o[k]).replace(';', ',') for k in
                         ('inn', 'predpriyatie', 'sayt', 'mashina', 'klass')) + '\n')
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(rq, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ')
for o in celi[:10]:
    print('  %-12s %-46s %s' % (o['inn'], (o['predpriyatie'] or 'ИМЕНИ НЕТ')[:46], o['mashina']))
print('\n########## ЧИСЛА')
print('  ИНН в парке всего          %5d' % len(park))
print('  поиск уже ходил по         %5d' % len(uzhe & set(park)))
print('  ЦЕЛЕЙ (по кому не ходил)   %5d' % len(celi))
print('  из них без названия        %5d  (слабая очередь)' % bez_imeni)
print('  с сайтом                   %5d' % sum(1 for o in celi if o['sayt']))
print('  --- по машине')
for k, v in collections.Counter(o['mashina'] for o in celi).most_common():
    print('     %-26s %5d' % (k, v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'парк': len(park), 'целей': len(celi), 'без имени': bez_imeni},
                           ensure_ascii=False))
