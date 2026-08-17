# -*- coding: utf-8 -*-
"""Кому именно отдали страницы и кто нашёлся вне базы — глазами."""
import io
import json
import os
import sys

D = r'C:\sender\server'
отдали, вне = [], []
p = os.path.join(D, 'hozyain_domena.jsonl')
if os.path.exists(p):
    for s in io.open(p, encoding='utf-8'):
        try:
            d = json.loads(s)
        except Exception:
            continue
        if d.get('итог') == 'хозяин в базе':
            отдали.append({'домен': d['домен'], 'был_у': d['был_у'], 'хозяин': d['хозяин'],
                           'имя': d.get('имя_хозяина', '')[:45],
                           'сайт_был': d.get('сайт_хозяина', '') or '—'})
q = os.path.join(D, 'hozyaeva_vne_bazy.jsonl')
if os.path.exists(q):
    for s in io.open(q, encoding='utf-8'):
        try:
            d = json.loads(s)
        except Exception:
            continue
        вне.append({'инн': d['inn'], 'домен': d['домен'], 'заголовок': (d.get('заголовок') or '')[:60]})
print(json.dumps({'отдали_примеры': отдали[:10], 'вне_базы_примеры': вне[:12],
                  'вне_базы_всего': len(вне)}, ensure_ascii=False, indent=1)[-3000:])
