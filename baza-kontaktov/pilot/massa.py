# -*- coding: utf-8 -*-
"""Массовый список: P1-шаблоны (с идеями моделей) × все регионы сегмента (segments_likely), без уже
прогнанных в пилоте. Порядок — по выходу новых в пилоте: экспортёры, орехи, ягоды, семеноводы,
элеваторы, пищевые; внутри — сильные регионы (agro_priority) первыми. Только Яндекс.
lr: известные коды из vyborka.LR, иначе 225/149 (регион и так есть в тексте запроса)."""
import csv, os
from vyborka import LR, minus_slova
D = os.path.dirname(os.path.abspath(__file__))
B = os.path.dirname(D)
ORDER = ['exporters', 'nuts', 'berries', 'seeds', 'elevators', 'food']
code = {'seeds': 'sem', 'elevators': 'elev', 'exporters': 'exp', 'food': 'food', 'nuts': 'nut', 'berries': 'berry'}
Z = [z for z in csv.DictReader(open(os.path.join(B, 'zaprosy.csv'), encoding='utf-8')) if z['priority'] == '1'
     and '{культура}' not in z['query_template'] and '{продукт}' not in z['query_template']]
R = list(csv.DictReader(open(os.path.join(B, 'regiony.csv'), encoding='utf-8')))
done = {p['query'].lower() for p in csv.DictReader(open(os.path.join(D, 'pilot_zaprosy.csv'), encoding='utf-8'))}
done |= {p['query'].lower() for p in csv.DictReader(open(os.path.join(D, 'idei_zaprosy.csv'), encoding='utf-8'))}
mins = minus_slova()
rows, seen = [], set()
for seg in ORDER:
    part = []
    for z in [z for z in Z if z['segment'] == seg]:
        t = z['query_template']
        by = z['geo_level'] == 'by'
        if '{регион}' in t:
            regs = [r for r in R if r['country'] == ('BY' if by else 'RU') and r['row_type'] in ('subject', 'oblast')
                    and code[seg] in r['segments_likely']]
        elif '{город}' in t:
            regs = [r for r in R if r['country'] == 'RU' and r['row_type'] == 'city' and code[seg] in r['segments_likely']]
        else:
            regs = [None]
        for r in regs:
            name = r['name_nom'] if r else ('Беларусь' if by or 'Беларус' in t else 'Россия')
            q = t.replace('{регион}', name).replace('{город}', name)
            if q.lower() in done or q.lower() in seen:
                continue
            seen.add(q.lower())
            parent = (r.get('parent_region') or name) if r else name
            pr = int(r['agro_priority'] or 3) if r and r.get('agro_priority') else 1
            lr = LR.get(name) or LR.get(parent) or (149 if (by or 'Беларус' in q) else 225)
            part.append((pr, {'segment': seg, 'subsegment': z['subsegment'], 'region': name,
                              'country': 'by' if (by or 'Беларус' in q) else 'ru', 'lr': lr, 'query': q,
                              'query_full': q + ' ' + ' '.join(mins.get('global', []) + mins.get(seg, [])),
                              'template': t}))
    part.sort(key=lambda x: x[0])
    rows += [p for _, p in part]
for i, r in enumerate(rows, 1):
    r['qid'] = f'm{i:05d}'
with open(os.path.join(D, 'massa_zaprosy.csv'), 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['qid', 'segment', 'subsegment', 'region', 'country', 'lr', 'query', 'query_full', 'template'])
    w.writeheader(); w.writerows(rows)
from collections import Counter
print(len(rows), Counter(r['segment'] for r in rows))
