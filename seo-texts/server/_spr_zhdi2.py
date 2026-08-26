# -*- coding: utf-8 -*-
"""Подождать и доложить: прогресс + примеры доказательств."""
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 700)
O = {}
for f in ('ozav_cards.jsonl', 'agro_cards.jsonl', 'spr_dokaz.jsonl'):
    p = r'C:\sender\_tmp\%s' % f
    O[f] = sum(1 for _ in io.open(p, encoding='utf-8', errors='replace')) \
        if os.path.exists(p) else 0
d = []
p = r'C:\sender\_tmp\spr_dokaz.jsonl'
if os.path.exists(p):
    for ln in io.open(p, encoding='utf-8', errors='replace'):
        try:
            d.append(json.loads(ln))
        except Exception:
            pass
св = {}
for r in d:
    s = св.setdefault(r['источник'], {'n': 0})
    s['n'] += 1
    s[r['улика']] = s.get(r['улика'], 0) + 1
O['улики'] = св
O['примеры'] = [[r['name'][:28], r['домен'], r['улика'], int(r['rev'] or 0) // 1000000]
                for r in d[:14]]
print(json.dumps(O, ensure_ascii=False)[:3000])
