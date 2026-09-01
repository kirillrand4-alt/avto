# -*- coding: utf-8 -*-
"""Отчёт: какие ещё группы (посадочные) можно сделать по разделу «Воздушные компрессоры».
Сравнивает ассортимент Битрикса с уже существующими фасетами/страницами."""
import json
from collections import defaultdict
from group_gap import load, index, FACETS, MIN, HAVE

data = load()
idx  = index(data)
N    = len(data)

def gap(key):
    have = HAVE.get(key, set())
    rows = sorted(((len(s), v) for v, s in idx[key].items() if len(s) >= MIN), reverse=True)
    if have == 'ALL':
        return [], rows
    new = [(n, v) for n, v in rows if v not in have]
    old = [(n, v) for n, v in rows if v in have]
    return new, old

print(f'РАЗДЕЛ «ВОЗДУШНЫЕ КОМПРЕССОРЫ»: {N} товаров в выгрузке Битрикса')
print(f'Порог группы: > 10 товаров\n')

print('=' * 78)
print('A. НОВЫЕ ФАСЕТЫ — свойств нет в текущем фильтре вообще')
print('=' * 78)
NEWF = ['tgroup','series','block','ipclass','temp','mobile','cooling','motor',
        'engine','warranty','noise','quiet','dewpt']
tot_a = 0
for k in NEWF:
    new, _ = gap(k)
    tot_a += len(new)
    print(f'\n{FACETS[k][0]}  →  {len(new)} групп')
    for n, v in new[:14]:
        print(f'     {n:>6}  {v}')
    if len(new) > 14:
        print(f'     … ещё {len(new)-14}')
print(f'\nИТОГО по A: {tot_a} новых групп')

print('\n' + '=' * 78)
print('B. ПРОБЕЛЫ В СУЩЕСТВУЮЩИХ ФАСЕТАХ — значения есть в наличии, страниц нет')
print('=' * 78)
tot_b = 0
for k in ['ctype','purpose','volt','recv','press','power','perf']:
    new, old = gap(k)
    tot_b += len(new)
    print(f'\n{FACETS[k][0]}  →  есть {len(old)}, НОВЫХ {len(new)}')
    for n, v in new[:20]:
        print(f'     {n:>6}  {v}')
    if len(new) > 20:
        print(f'     … ещё {len(new)-20}')
print(f'\nИТОГО по B: {tot_b} новых групп')

print('\n' + '=' * 78)
print('C. ПАРНЫЕ КОМБИНАЦИИ (фасет × фасет), > 10 товаров')
print('=' * 78)
PAIRS = [('brand','power'),('brand','press'),('brand','recv'),('brand','ctype'),
         ('brand','vsdflag'),('brand','purpose'),('brand','series'),
         ('ctype','power'),('ctype','press'),('ctype','purpose'),('ctype','country'),
         ('country','power'),('country','press'),('purpose','power'),('purpose','press'),
         ('power','press'),('power','vsdflag'),('power','recvflag'),('power','dryflag'),
         ('block','power'),('ipclass','power'),('temp','brand'),('mobile','brand')]
tot_c = 0
for a, b in PAIRS:
    cnt = 0
    for va, sa in idx[a].items():
        if len(sa) < MIN: continue
        for vb, sb in idx[b].items():
            if len(sb) < MIN: continue
            if len(sa & sb) >= MIN: cnt += 1
    tot_c += cnt
    print(f'{FACETS[a][0]:<26} × {FACETS[b][0]:<26} {cnt:>6}')
print(f'\nИТОГО по C (только эти 23 пары): {tot_c}')
