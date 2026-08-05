# -*- coding: utf-8 -*-
"""Сбор по каждому источнику ПОСЛЕ трёх правок. Свежих уникальных и сколько из них ПРЯМЫХ.

Правки этого тика, все на живом `C:\\sender\\server\\news_scan.py`:
    col_hh          + два заголовка (токен)          замер 0 -> 88 items
    fetch_article   + заслон на оболочку, три захода  замер: провалов пробы 0

Теперь считаю, что стало на входе стадии A. Зову коллекторы с ИХ ЖЕ боевыми умолчаниями,
а не с пустыми: прошлый мой замер дал ВК ноль просто потому, что я позвала его без токена
и без запросов — дефект прибора, не коллектора. Поэтому сигнатуру каждого коллектора
смотрю через `inspect`, а не угадываю.

Провайдера не трогаю: ПРЯМОЙ/КОСВЕННЫЙ считаю своей мерой повода прямо здесь. seen_news
только читаю.
"""
import collections
import inspect
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

MASHINA = re.compile(
    r'компрессор\w*|турбокомпрессор\w*|газодувк\w+|газодувн\w+|воздуходувк\w+|'
    r'нагнетател\w+|воздухоразделен\w+|\bВРУ\b|сжат\w+\s+воздух\w*|пневмат\w+|'
    r'генератор\w*\s+(?:азота|кислорода)|азотн\w+\s+станци\w+|кислородн\w+\s+станци\w+|'
    r'\bазот\w*\b|\bкислород\w*\b|\bчиллер\w*|осушител\w+', re.I)
PROIZV = re.compile(
    r'\b\w*завод\w*|\bцех\w*|\bпроизводств\w*|\b\w*комбинат\w*|\bфабрик\w*|\bэлеватор\w*|'
    r'\bмощност\w+\s+\d|\bагрегат\w*|\bустановк\w+|\bпереработк\w+|\bобогатительн\w+|'
    r'\bНПЗ\b|\bГОК\b|\bТЭЦ\b|\bдобыч\w+|\bшахт\w+', re.I)


def povod(t):
    if MASHINA.search(t or ''):
        return 'ПРЯМОЙ'
    return 'КОСВЕННЫЙ' if PROIZV.search(t or '') else 'ПРОЧЕЕ'


kluchi = set()
try:
    cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
    kluchi = set(r[0] for r in cx.execute('select k from seen_news'))
    cx.close()
except Exception:  # noqa: BLE001
    pass
print('ключей в seen_news: %d' % len(kluchi))

print('\n=== СИГНАТУРЫ КОЛЛЕКТОРОВ (чтобы звать как бой, а не как придумалось)')
for n in sorted(x for x in dir(NS) if x.startswith('col_')):
    try:
        print('  %-18s %s' % (n, inspect.signature(getattr(NS, n))))
    except Exception:  # noqa: BLE001
        pass

ZAK = ['компрессорная установка', 'компрессор винтовой', 'генератор азота',
       'генератор кислорода', 'осушитель сжатого воздуха']


def gugl():
    inds = list(NS.KC_INDUSTRIES) + list(NS.MEYER_INDUSTRIES)
    return ['%s %s' % (t, i) for t in NS.TRIGGERS[:4] for i in inds]


zovy = [
    ('hh', lambda: NS.col_hh(NS.HH_SIGNALS, '113', 14, 10)),
    ('google', lambda: NS.col_google(gugl(), 14, 10)),
    ('zakupki', lambda: NS.col_zakupki(ZAK, 14, 10)),
    ('frp', lambda: NS.col_frp(14, 30)),
    ('regional', lambda: NS.col_regional(NS._load_feeds_catalog(), 14, 10)),
]
if hasattr(NS, 'col_vk'):
    p = list(inspect.signature(NS.col_vk).parameters)
    tok = os.environ.get('VK_TOKEN', '')
    print('\ncol_vk параметры: %s ; токен в окружении: %s' % (p, bool(tok)))

itog, glazami = {}, []
for imya, zov in zovy:
    try:
        items = zov() or []
    except Exception as e:  # noqa: BLE001
        itog[imya] = {'упал': '%s: %s' % (type(e).__name__, str(e)[:80])}
        print('\n%s УПАЛ: %s' % (imya, str(e)[:140]))
        continue
    vid, novye = set(), []
    for it in items:
        try:
            k = NS._news_key(it)
        except Exception:  # noqa: BLE001
            continue
        if k in vid:
            continue
        vid.add(k)
        if k not in kluchi:
            novye.append(it)
    sch = collections.Counter(povod(str(i.get('title') or '')) for i in novye)
    itog[imya] = {'сырых': len(items), 'уникальных': len(vid), 'НОВЫХ': len(novye),
                  'ПРЯМЫХ': sch['ПРЯМОЙ'], 'косвенных': sch['КОСВЕННЫЙ'],
                  'прочее': sch['ПРОЧЕЕ']}
    for it in novye:
        if povod(str(it.get('title') or '')) == 'ПРЯМОЙ' and len(glazami) < 10:
            glazami.append((imya, it))

print('\n\n########## ДЕСЯТЬ ПРЯМЫХ ПОВОДОВ ГЛАЗАМИ')
for imya, it in glazami:
    print('\n  [%s] %s' % (imya, str(it.get('title') or '')[:130]))
    print('        %s' % str(it.get('link') or '')[:110])

print('\n\n########## ПО ИСТОЧНИКАМ (цель — 10 свежих уникальных)')
print('  %-10s %6s %6s %6s | %6s %6s %6s' % ('источник', 'сырых', 'уник', 'НОВЫХ',
                                             'прямых', 'косв', 'прочее'))
for k, v in itog.items():
    if 'упал' in v:
        print('  %-10s УПАЛ: %s' % (k, v['упал']))
        continue
    print('  %-10s %6d %6d %6d | %6d %6d %6d'
          % (k, v['сырых'], v['уникальных'], v['НОВЫХ'], v['ПРЯМЫХ'],
             v['косвенных'], v['прочее']))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
