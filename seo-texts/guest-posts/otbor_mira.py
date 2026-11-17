#!/usr/bin/env python3
"""Топ доноров ТОЛЬКО с Miralinks (цена в поле mira donory-principy.json).

Строгая мерка = трафик Google (g_tr) x доля трафика на статьи промышленной темы
(statya_strict из donory-klass.jsonl). Отсев: токсичность >= 5%, ферма (исх/вх >= 25),
конкуренты. Выход: печать таблицы + otbor-mira.json.
"""
import json
import os

DIR = os.path.dirname(os.path.abspath(__file__))
KONK = {'ariacom.ru'}  # конкуренты владельца - не покупаем

P = {d['domain']: d for d in json.load(open(os.path.join(DIR, 'donory-principy.json'), encoding='utf-8'))}
K = {}
for l in open(os.path.join(DIR, 'donory-klass.jsonl'), encoding='utf-8'):
    r = json.loads(l)
    K[r['domain']] = r

C = json.load(open(os.path.join(DIR, 'mira-ceny.json'), encoding='utf-8'))  # цены из выгрузки Miralinks 10.11

rows, out = [], []
for dom, k in K.items():
    p = P.get(dom, {})
    price = p.get('mira') or (C.get(dom) or {}).get('price')
    if not price or dom in KONK:
        continue
    g = p.get('g_tr') or k.get('traffic_top') or 0  # нет обзора Semrush - сумма трафика топ-100 запросов
    why = []
    if (k.get('toxic') or 0) >= 0.05:
        why.append(f"токсичн {k['toxic']:.0%}")
    if ((C.get(dom) or {}).get('spam') or 0) >= 5:
        why.append(f"спам Я {C[dom]['spam']}%")
    if (p.get('out_in') or 0) >= 25:
        why.append(f"ферма {p['out_in']}")
    rec = {'domain': dom, 'tema': p.get('tema'), 'tip': p.get('tip'), 'n': p.get('n'),
           'g_tr': g, 'g_dyn': p.get('g_dyn'), 'mira': price, 'url': (C.get(dom) or {}).get('url'),
           'strict': round(g * (k.get('statya_strict') or 0)),
           'wide': round(g * (k.get('statya_prom') or 0)),
           'toxic': k.get('toxic'), 'razdel': k.get('razdel'), 'otsev': ', '.join(why),
           'top': k.get('top_statyi', [])[:3]}
    (out if why else rows).append(rec)

rows.sort(key=lambda r: (-r['strict'], -r['wide']))
json.dump({'top': rows, 'otsev': out}, open(os.path.join(DIR, 'otbor-mira.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('Miralinks с разметкой:', len(rows) + len(out), 'отсеяно:', len(out))
for i, r in enumerate(rows[:30], 1):
    print(f"{i:2} {r['domain']:26} строг {r['strict']:6} шир {r['wide']:6} G {r['g_tr']:7} "
          f"x{r['g_dyn']} {r['mira']:>6} ₽  {r['tema']}/{r['tip']} конк {r['n']}")
print('-- отсев:')
for r in out:
    print(f"   {r['domain']:26} {r['otsev']}  строг {r['strict']}")
