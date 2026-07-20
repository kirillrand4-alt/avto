# -*- coding: utf-8 -*-
"""Разбор колонок ПРИОРИТЕТА в базе обзвона (стрим 679МБ через stdin).
Смотрим распределения: Итоговый балл приоритета, Макс. балл по связке,
Приоритет × выручка / 10000, + связка приоритет×направление/ОКВЭД. LLM не нужен."""
import os, sys, csv, json, re
from collections import Counter, defaultdict

D = os.path.dirname(os.path.abspath(__file__))
csv.field_size_limit(10 * 1024 * 1024)

rd = csv.reader(sys.stdin, delimiter=';')
header = [h.lstrip('﻿').strip() for h in next(rd)]
def col(n): return header.index(n) if n in header else -1

# показать все заголовки, чтобы точно знать имена колонок приоритета
sys.stderr.write('ЗАГОЛОВКИ (индекс: имя):\n')
for i,h in enumerate(header):
    sys.stderr.write(f'  {i:>2}: {h}\n')
sys.stderr.flush()

I_BAZA = col('База')
I_TOTAL = col('Итоговый балл приоритета')
I_MAX   = col('Макс. балл по связке')
I_PXR   = col('Приоритет × выручка / 10000')
I_COMMENT = col('Комментарий расчёта')
I_REV = col('Выручка, руб.')
I_EQMAIN = col('Оборудование по основному ОКВЭД')

def fnum(s):
    s = (s or '').strip().replace(' ','').replace('\xa0','').replace(',','.')
    if not s: return None
    try: return float(re.sub(r'[^0-9.\-]','',s))
    except ValueError: return None

total_hist = Counter()   # округл. Итоговый балл
max_hist = Counter()     # Макс. балл по связке (ожидаем 1..5)
pxr_buckets = Counter()
have_total = have_max = have_pxr = 0
max_by_baza = defaultdict(Counter)     # направление -> распределение макс.балла
max_by_eq = defaultdict(Counter)       # оборудование -> макс.балл
# для «топ по приоритету» — комбо
combo = []   # (max, total, pxr, baza, eqmain)
rows = 0

def bucket_pxr(v):
    if v is None: return 'н/д'
    if v<=0: return '0'
    if v<10: return '<10'
    if v<100: return '10-100'
    if v<1000: return '100-1k'
    if v<10000: return '1k-10k'
    if v<100000: return '10k-100k'
    return '100k+'

for row in rd:
    rows += 1
    if len(row) <= max(I_TOTAL,I_MAX,I_PXR,I_BAZA): continue
    t = fnum(row[I_TOTAL]) if I_TOTAL>=0 else None
    m = fnum(row[I_MAX]) if I_MAX>=0 else None
    p = fnum(row[I_PXR]) if I_PXR>=0 else None
    baza = (row[I_BAZA].strip() if I_BAZA>=0 else '') or '(пусто)'
    eq = (row[I_EQMAIN].strip() if I_EQMAIN>=0 else '')
    if t is not None:
        total_hist[round(t)] += 1; have_total += 1
    if m is not None:
        max_hist[round(m,1)] += 1; have_max += 1
        max_by_baza[baza][round(m)] += 1
        if eq: max_by_eq[eq][round(m)] += 1
    if p is not None:
        pxr_buckets[bucket_pxr(p)] += 1; have_pxr += 1

out = {
 'rows': rows,
 'columns_present': {'Итоговый балл приоритета': I_TOTAL>=0, 'Макс. балл по связке': I_MAX>=0,
                     'Приоритет × выручка / 10000': I_PXR>=0, 'Комментарий расчёта': I_COMMENT>=0},
 'have': {'total': have_total, 'max': have_max, 'pxr': have_pxr},
 'max_score_hist': dict(sorted(max_hist.items())),
 'total_score_hist': dict(sorted(total_hist.items())[:40]),
 'pxr_buckets': dict(pxr_buckets),
 'max_by_baza': {b: dict(sorted(c.items())) for b,c in max_by_baza.items()},
 'max_by_eq_top': {},
}
# топ оборудования по доле максимального приоритета (m>=4)
eq_rank = []
for eq,c in max_by_eq.items():
    tot = sum(c.values())
    hi = sum(v for k,v in c.items() if k>=4)
    if tot>=200:
        eq_rank.append((eq, tot, hi, round(100*hi/tot,1)))
eq_rank.sort(key=lambda x:-x[3])
out['max_by_eq_top'] = [{'eq':e,'total':t,'hi(4-5)':h,'hi_pct':p} for e,t,h,p in eq_rank[:25]]

json.dump(out, open(os.path.join(D,'priority-analysis.json'),'w'), ensure_ascii=False, indent=1)

w=sys.stderr.write
w(f"\n=== ПРИОРИТЕТ: {rows} строк ===\n")
w(f"колонки: {out['columns_present']}\n")
w(f"заполнено: total={have_total}, max={have_max}, pxr={have_pxr}\n")
w(f"\nМАКС. БАЛЛ ПО СВЯЗКЕ (1-5):\n")
for k,v in sorted(max_hist.items()): w(f"  {k}: {v}\n")
w(f"\nПРИОРИТЕТ × ВЫРУЧКА / 10000 (бакеты):\n")
for k in ['0','<10','10-100','100-1k','1k-10k','10k-100k','100k+','н/д']:
    if k in pxr_buckets: w(f"  {k}: {pxr_buckets[k]}\n")
w(f"\nМАКС.БАЛЛ по направлению (База):\n")
for b,c in max_by_baza.items():
    w(f"  {b}: {dict(sorted(c.items()))}\n")
