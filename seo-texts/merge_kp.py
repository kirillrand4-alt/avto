# -*- coding: utf-8 -*-
"""Слияние всех структуризаций КП в мульти-брендовую базу kb/kp-base-all.json.
Приоритет при конфликте: презентация(3) > каталог/прайс(2) > КП(1). Отчёт: kb/kp-base-report.md"""
import json, os, re
from collections import Counter, defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
STR = os.path.join(DIR, 'kp-work', 'struct')
PRIO = {'презентация': 3, 'каталог': 2, 'прайс': 2, 'КП': 1}

def norm_brand(b):
    b = re.sub(r'[^a-zа-я0-9 ]', '', str(b or '').lower()).strip()
    alias = {'атлас копко': 'atlas copco', 'кросс эйр': 'cross air', 'энгер': 'enger'}
    return alias.get(b, b) or None

docs = []
for f in os.listdir(STR):
    try:
        d = json.load(open(os.path.join(STR, f)))
    except Exception:
        continue
    if '_error' not in d:
        docs.append(d)

brands = defaultdict(lambda: {'models': {}, 'series': Counter(), 'blocks': Counter(),
                              'warranties': Counter(), 'claims': Counter(), 'docs': 0})
skipped = 0
for d in sorted(docs, key=lambda x: PRIO.get(x.get('doc_type'), 0)):
    b = norm_brand(d.get('brand'))
    if not b:
        skipped += 1; continue
    B = brands[b]; B['docs'] += 1
    pr = PRIO.get(d.get('doc_type'), 0)
    for s in (d.get('series') or []):
        if s: B['series'][str(s)[:30]] += 1
    for m in (d.get('models') or []):
        name = (m.get('model') or '').strip()
        if len(name) < 3: continue
        cur = B['models'].setdefault(name, {'_prio': -1})
        for k, v in m.items():
            if v in (None, '', []) or k == 'model': continue
            if k not in cur or cur['_prio'] <= pr:
                cur[k] = v
        cur['_prio'] = max(cur['_prio'], pr)
        if m.get('screw_block'): B['blocks'][str(m['screw_block'])[:24]] += 1
    if d.get('warranty'): B['warranties'][str(d['warranty'])[:90]] += 1
    for c in (d.get('company_claims') or []): B['claims'][str(c)[:90]] += 1

out = {}
rep = ['# Мульти-брендовая КП-база\n', f'Документов слито: {len(docs)} (без бренда: {skipped})\n',
       '| Бренд | Документов | Моделей | с кВт | Топ-серии |', '|---|---|---|---|---|']
for b, B in sorted(brands.items(), key=lambda kv: -len(kv[1]['models'])):
    for v in B['models'].values(): v.pop('_prio', None)
    out[b] = {'models': B['models'], 'series': dict(B['series'].most_common(15)),
              'screw_blocks': dict(B['blocks'].most_common(8)),
              'warranties': dict(B['warranties'].most_common(4)),
              'company_claims': dict(B['claims'].most_common(10)), 'docs': B['docs']}
    kw = sum(1 for m in B['models'].values() if m.get('power_kvt'))
    rep.append(f"| {b} | {B['docs']} | {len(B['models'])} | {kw} | {', '.join(list(B['series'])[:4])} |")
json.dump(out, open(os.path.join(DIR, 'kb', 'kp-base-all.json'), 'w'), ensure_ascii=False, indent=1)
open(os.path.join(DIR, 'kb', 'kp-base-report.md'), 'w').write('\n'.join(rep))
print(f'брендов: {len(out)} | моделей всего: {sum(len(v["models"]) for v in out.values())}')
print('\n'.join(rep[2:14]))
