# -*- coding: utf-8 -*-
"""Зависит ли отдача канала от ЧИСЛА источников, назвавших человека. Проверить догадку.

НАБЛЮДЕНИЕ, КОТОРОЕ НАДО ЛИБО ПОДТВЕРДИТЬ, ЛИБО ОТБРОСИТЬ. Последний кусок из 58 имён
дал 39 телефонов — 67 процентов, при 5-10 на широком списке. У 45 из этих 58 имя было
названо ДВУМЯ И БОЛЕЕ источниками независимо.

Догадка: человек, названный несколькими списками, чаще имеет открытый номер, потому
что он вообще заметнее — он ведёт закупки, подписывает документы, стоит на страницах.

Догадка красивая, и именно поэтому её надо проверить, а не принять. Считаю отдачу по
всему потоку в разрезе «сколько источников назвали человека». Если разница есть, она
даёт правило отбора: спрашивать сперва тех, кого назвали дважды, и это дешевле в разы.
Если разницы нет — 67 процентов были свойством конкретной пачки, и правила нет.
"""
import collections
import csv
import json
import os
import re

VHOD = r'C:\sender\_ops\3s_p25_obratnyy_vhod.csv'
SPLOSH = r'C:\sender\_ops\3s_p25_vhod_sploshnoy.csv'
POTOK = r'C:\sender\_ops\p25-obratnyy.jsonl'
csv.field_size_limit(10 ** 8)


def klyuch(f):
    return re.sub(r'\s+', ' ', str(f or '').strip()).lower()


def lichnyy(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


# Сколько источников назвали человека — из широкого входа, там это записано числом.
istochnikov = {}
if os.path.exists(SPLOSH):
    for r in csv.DictReader(open(SPLOSH, encoding='utf-8-sig'), delimiter=';'):
        n = (r.get('istochnikov') or '').strip()
        if r.get('fio') and n.isdigit():
            istochnikov[klyuch(r['fio'])] = int(n)

sch = collections.Counter()
po_ist = collections.defaultdict(lambda: {'спрошено': 0, 'с телефоном': 0,
                                          'с ЛИЧНЫМ мобильным': 0})
for ln in open(POTOK, encoding='utf-8'):
    try:
        z = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    if z.get('err'):
        continue
    f = klyuch(z.get('fio'))
    n = istochnikov.get(f)
    # Про кого число источников неизвестно — отдельная корзина, а не приписанная к «1».
    gruppa = ('источников неизвестно' if n is None
              else ('1 источник' if n == 1 else '2 и более источников'))
    d = po_ist[gruppa]
    d['спрошено'] += 1
    kont = [k for k in (z.get('kontakty') or []) if isinstance(k, dict)]
    tel = [k for k in kont if (k.get('tip') or 'телефон') == 'телефон' and k.get('znachenie')]
    if tel:
        d['с телефоном'] += 1
    if any(lichnyy(k.get('znachenie')) for k in tel):
        d['с ЛИЧНЫМ мобильным'] += 1

for g, d in sorted(po_ist.items()):
    if not d['спрошено']:
        continue
    print('  %-24s спрошено %5d | с телефоном %4d (%4.1f%%) | ЛИЧНЫЙ МОБИЛЬНЫЙ %4d (%4.1f%%)'
          % (g, d['спрошено'], d['с телефоном'], 100.0 * d['с телефоном'] / d['спрошено'],
             d['с ЛИЧНЫМ мобильным'],
             100.0 * d['с ЛИЧНЫМ мобильным'] / d['спрошено']))
print('ИТОГ ' + json.dumps({
    'групп': len(po_ist),
    'людей с известным числом источников': sum(
        d['спрошено'] for g, d in po_ist.items() if 'неизвестно' not in g),
}, ensure_ascii=False))
