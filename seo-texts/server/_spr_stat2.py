# -*- coding: utf-8 -*-
"""Проверка своего же счёта: примеры по слоям checko-выборки + прогресс каталогов."""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
O = {}
recs = [json.loads(l) for l in io.open(r'C:\sender\_tmp\checko_sample.jsonl',
                                       encoding='utf-8', errors='replace') if l.strip()]
O['всего'] = len(recs)
for сл in ('топ', 'с_выручкой', 'без_выручки'):
    g = [r for r in recs if r['слой'] == сл]
    O[сл] = {
        'n': len(g),
        'медиана_выручки_млн': round(sorted(int(x['rev']) for x in g)[len(g) // 2] / 1e6, 1) if g else 0,
        'с_сайтом': [[x['name'][:26], x.get('sites'), int(x['rev'] / 1e6)]
                     for x in g if x.get('sites')][:6],
        'без_сайта_примеры': [[x['name'][:30], int(x['rev'] / 1e6), (x.get('emails') or [])[:2]]
                              for x in g if not x.get('sites')][:6],
        'via_proxy': sum(1 for x in g if x.get('via') == 'proxy'),
        'сайт_через_прокси': sum(1 for x in g if x.get('via') == 'proxy' and x.get('sites')),
        'сайт_напрямую': sum(1 for x in g if x.get('via') != 'proxy' and x.get('sites')),
        'напрямую_n': sum(1 for x in g if x.get('via') != 'proxy'),
    }
for f in ('ozav_cards.jsonl', 'agro_apk_sample.jsonl'):
    p = r'C:\sender\_tmp\%s' % f
    if os.path.exists(p):
        z = [json.loads(l) for l in io.open(p, encoding='utf-8', errors='replace') if l.strip()]
        O[f] = {'n': len(z), 'с_сайтом': sum(1 for x in z if x.get('site') or x.get('ext')),
                'с_инн': sum(1 for x in z if x.get('inn'))}
for f in ('spr_ozav.log', 'spr_apk.log'):
    try:
        O.setdefault('логи', {})[f] = open(r'C:\sender\_tmp\%s' % f,
                                           encoding='utf-8', errors='replace').read()[-160:]
    except Exception as e:
        O.setdefault('логи', {})[f] = str(e)[:50]
print(json.dumps(O, ensure_ascii=False)[:5700])
