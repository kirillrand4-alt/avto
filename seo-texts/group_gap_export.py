# -*- coding: utf-8 -*-
"""Выгрузка кандидатов в новые посадочные группы: полный список + шорт-лист."""
import csv, re, json
from group_gap import load, index, FACETS, MIN, HAVE

data = load(); idx = index(data)

# --- отсев мусорных значений ---------------------------------------------
JUNK = re.compile(r'(Стандартная комплектация|^Стандартный)')
def clean(k, v):
    if JUNK.search(v): return False
    if k in ('mobile','quiet','recvflag','dryflag','vsdflag','cooling') and v == 'нет': return False
    if k == 'motor' and v == 'Электрический': return False
    if k == 'ipclass' and v in ('IP55','IP54','IP23'): return False   # 90% ассортимента, не сегмент
    if k == 'warranty' and v == '1 год': return False
    if k == 'noise':                      # шум — только круглые «до N дБ»
        return False
    if k == 'power':                      # только осмысленный ряд мощностей
        try: f = float(v)
        except ValueError: return False
        return (f in {1.5,2.2,3,4,5,18,24,26,33,60,80,280,450} or (f >= 8 and f == int(f) and int(f) % 10 == 0))
    if k == 'press':
        try: f = float(v)
        except ValueError: return False
        return f in {1,1.5,2,3,4,4.5,6.5,7.5,8.5,9,9.5,10.5,12.5,14,17,18,21,22,24,35,350}
    if k == 'perf':                       # круглые «м³/мин» + круглые сотни/тысячи л/мин
        try: f = float(v)
        except ValueError: return False
        return (f >= 1000 and f % 1000 == 0) or (f < 1000 and f % 100 == 0)
    if k == 'recv':
        try: f = float(v)
        except ValueError: return False
        return f in {24,36,50,90,100,120,140,150,160,180,230,240,270,300,350,540,750}
    return True

GROUP_A = ['tgroup','series','block','ipclass','temp','mobile','cooling','motor',
           'engine','warranty','quiet','dewpt','noise']
GROUP_B = ['ctype','purpose','volt','recv','press','power','perf']

rows = []
for k in GROUP_A + GROUP_B:
    have = HAVE.get(k, set())
    if have == 'ALL': continue
    kind = 'новый фасет' if k in GROUP_A else 'пробел в фасете'
    for v, s in idx[k].items():
        n = len(s)
        if n < MIN or v in have: continue
        rows.append({'блок': kind, 'фасет': FACETS[k][0], 'ключ': k,
                     'значение': v, 'товаров': n, 'шорт-лист': 'да' if clean(k, v) else ''})

rows.sort(key=lambda r: (-r['товаров'],))
with open('group-gap-candidates.csv','w',newline='',encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['блок','фасет','ключ','значение','товаров','шорт-лист'], delimiter=';')
    w.writeheader(); w.writerows(rows)

short = [r for r in rows if r['шорт-лист']]
print(f'всего кандидатов (>10 товаров): {len(rows)}')
print(f'в шорт-листе: {len(short)}')
print()
from collections import Counter
c = Counter((r['блок'], r['фасет']) for r in rows)
cs = Counter((r['блок'], r['фасет']) for r in short)
print(f'{"фасет":<34} {"всего":>6} {"шорт":>6}')
for (b, fname), n in c.most_common():
    print(f'{fname:<34} {n:>6} {cs[(b,fname)]:>6}   [{b}]')

# --- пары: только осмысленные, для шорт-листа -----------------------------
PAIRS = [('brand','power'),('brand','press'),('brand','ctype'),('brand','series'),
         ('ctype','power'),('ctype','press'),('ctype','purpose'),('country','power'),
         ('purpose','power'),('block','power'),('temp','brand'),('mobile','brand'),
         ('brand','vsdflag'),('brand','recv')]
pr = []
for a, b in PAIRS:
    n = sum(1 for va, sa in idx[a].items() if len(sa) >= MIN
              for vb, sb in idx[b].items() if len(sb) >= MIN and len(sa & sb) >= MIN)
    pr.append((FACETS[a][0], FACETS[b][0], n))
print()
print('ПАРЫ (>10 товаров в пересечении):')
for a, b, n in pr: print(f'  {a} × {b}: {n}')
print('  ИТОГО пар:', sum(n for _,_,n in pr))
json.dump({'single_total': len(rows), 'single_short': len(short),
           'pairs': [{'a':a,'b':b,'n':n} for a,b,n in pr]},
          open('group-gap-summary.json','w'), ensure_ascii=False, indent=1)
