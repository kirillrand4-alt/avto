# -*- coding: utf-8 -*-
"""Сравнение v2 (до починки поиска) и v3 (после): матрица переходов релевантности,
починенные/сломанные фразы, спотлайт по конкретным болям из OTCHET-poisk-v2."""
import json
from collections import Counter

def load(path_eval, path_res):
    ev = {e['phrase']: e for e in json.load(open(path_eval))}
    rs = {}
    for l in open(path_res):
        r = json.loads(l)
        rs[r['phrase']] = r
    return ev, rs

ev2, rs2 = load('inventory/search-eval-v2.json', 'inventory/search-results-v2.jsonl')
ev3, rs3 = load('inventory/search-eval.json', 'inventory/search-results.jsonl')

common = [p for p in ev2 if p in ev3]
print(f'общих фраз с оценками: {len(common)}')

trans = Counter((ev2[p]['relevance'], ev3[p]['relevance']) for p in common)
print('\nматрица переходов (v2 -> v3): счёт')
for (a, b), n in sorted(trans.items()):
    mark = 'починено' if b > a else ('РЕГРЕСС' if b < a else '')
    print(f'  {a} -> {b}: {n} {mark}')

fixed = sorted(p for p in common if ev3[p]['relevance'] > ev2[p]['relevance'])
regr = sorted(p for p in common if ev3[p]['relevance'] < ev2[p]['relevance'])
print(f'\nстало лучше: {len(fixed)} | стало хуже: {len(regr)}')
json.dump({'fixed': fixed, 'regressed': regr},
          open('inventory/diff-v2-v3.json', 'w'), ensure_ascii=False, indent=1)
print('регрессы:')
for p in regr:
    print(f'  - {p!r}: {ev2[p]["relevance"]}->{ev3[p]["relevance"]} '
          f'{ev3[p]["fail_type"]}: {ev3[p]["note"][:80]}')

# пустые выдачи (жёсткий AND) и сообщение «ничего не найдено»
for tag, rs in (('v2', rs2), ('v3', rs3)):
    zero = [p for p in common if rs[p].get('found') == 0]
    marker = [p for p in zero if rs[p].get('empty_marker')]
    print(f'\n{tag}: пустых выдач {len(zero)}, из них с сообщением «ничего не найдено»: {len(marker)}')

SPOT = ['Ironmac IC 10 10', 'Atlas Copco GA 55', 'atlas copco ga55', 'Cross Air CA 22',
        'DALGAKIRAN DKK 40', 'BERG ВК-18', 'Enger LC-11DFR-500 16', 'atlas cd 250',
        'et ofs 5', 'поршневой компрессор', 'купить поршневой компрессор',
        'модульные компрессорные станции', 'азотное оборудование']
print('\n=== спотлайт по болям из v2 ===')
for q in SPOT:
    hits = [p for p in common if q.lower() in p.lower()] if q not in ev2 else [q]
    for p in hits[:2]:
        t2 = [t['name'][:60] for t in rs2[p].get('top', [])[:3]]
        t3 = [t['name'][:60] for t in rs3[p].get('top', [])[:3]]
        print(f'\n«{p}»  rel {ev2[p]["relevance"]} -> {ev3[p]["relevance"]}, '
              f'found {rs2[p].get("found")} -> {rs3[p].get("found")}')
        print(f'  v2 топ: {t2}')
        print(f'  v3 топ: {t3}')
