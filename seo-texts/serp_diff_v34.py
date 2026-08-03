# -*- coding: utf-8 -*-
"""Отделяем реальные изменения выдачи от разброса ИИ-оценщика: для каждого перехода
релевантности смотрим, изменился ли сам топ-10 (URL) между v3 и v4."""
import json
from collections import Counter

def load(path_eval, path_res):
    ev = {e['phrase']: e for e in json.load(open(path_eval))}
    rs = {r['phrase']: r for l in open(path_res) for r in [json.loads(l)]}
    return ev, rs

ev2, rs2 = load('inventory/search-eval-v3.json', 'inventory/search-results-v3.jsonl')
ev3, rs3 = load('inventory/search-eval.json', 'inventory/search-results.jsonl')
common = [p for p in ev2 if p in ev3]

def serp_key(r):
    return (r.get('found'), tuple(t['url'] for t in r.get('top', [])))

same = [p for p in common if serp_key(rs2[p]) == serp_key(rs3[p])]
diff = [p for p in common if p not in set(same)]
print(f'выдача идентична v2: {len(same)} фраз | выдача изменилась: {len(diff)} фраз')

def split(pl):
    up = sum(1 for p in pl if ev3[p]['relevance'] > ev2[p]['relevance'])
    dn = sum(1 for p in pl if ev3[p]['relevance'] < ev2[p]['relevance'])
    eq = len(pl) - up - dn
    return up, dn, eq

for name, pl in (('выдача ИЗМЕНИЛАСЬ', diff), ('выдача ИДЕНТИЧНА (разброс оценщика)', same)):
    up, dn, eq = split(pl)
    print(f'{name}: лучше {up}, хуже {dn}, без изменений {eq}')

noise_regr = [p for p in same if ev3[p]['relevance'] < ev2[p]['relevance']]
real_regr = [p for p in diff if ev3[p]['relevance'] < ev2[p]['relevance']]
real_fix = [p for p in diff if ev3[p]['relevance'] > ev2[p]['relevance']]
json.dump({'serp_same': len(same), 'serp_diff': len(diff),
           'real_fixed': sorted(real_fix), 'real_regressed': sorted(real_regr),
           'judge_noise_regressed': sorted(noise_regr)},
          open('inventory/serp-diff-v34.json', 'w'), ensure_ascii=False, indent=1)
print(f'\nреально починено (выдача менялась, стало лучше): {len(real_fix)}')
print(f'реально хуже (выдача менялась, стало хуже): {len(real_regr)}')
print(f'шум оценщика в «регрессах» (выдача та же): {len(noise_regr)}')
print('\nреальные регрессы (топ изменился и стало хуже):')
for p in sorted(real_regr):
    print(f'  - {p!r}: {ev2[p]["relevance"]}->{ev3[p]["relevance"]} | {ev3[p]["note"][:90]}')
