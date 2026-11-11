#!/usr/bin/env python3
"""Пересечение ссылочных доноров конкурентов: домены, которые ссылаются на 2+ конкурентов.

    python3 konkurenty_peresechenie.py [konkurenty-refdomains.jsonl] -> konkurenty-peresechenie.json

Строка seRefdomains: [1] корневой домен, [6] спам, [9] DR, [12] трафик, [16] dofollow-ссылок.
n - на скольких конкурентов ссылается домен; do - сумма dofollow; кто - список конкурентов.
"""
import collections
import json
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DIR, 'konkurenty-refdomains.jsonl')
OUT = os.path.join(DIR, 'konkurenty-peresechenie.json')


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


agg = collections.defaultdict(lambda: {'n': 0, 'dr': 0.0, 'tr': 0.0, 'do': 0.0, 'kto': []})
for line in open(SRC, encoding='utf-8'):
    if not line.strip():
        continue
    d = json.loads(line)
    seen = set()
    for r in d['rows']:
        dom = r[1]
        if dom in seen:
            continue
        seen.add(dom)
        a = agg[dom]
        a['n'] += 1
        a['dr'] = max(a['dr'], num(r[9]))
        a['tr'] = max(a['tr'], num(r[12]))
        a['do'] += num(r[16])
        a['kto'].append(d['target'])
MIN_TR = float(os.environ.get('MIN_TR', '100'))
# ссылочные фермы (.store/.shop/.agency без трафика) отсекает порог трафика
res = [{'domain': k, **v} for k, v in agg.items() if v['n'] >= 2 and v['tr'] >= MIN_TR]
res.sort(key=lambda x: (-x['n'], -x['tr']))
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(f'доменов с 2+ конкурентами и трафиком от {MIN_TR:.0f}: {len(res)} (конкурентов в выборке: '
      f'{sum(1 for l in open(SRC, encoding="utf-8") if l.strip())})')
for x in res[:25]:
    print(f"{x['n']:3d} {x['domain']:32s} DR {x['dr']:4.0f} трафик {x['tr']:9.0f} dofollow {x['do']:5.0f}")
