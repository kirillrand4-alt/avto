# -*- coding: utf-8 -*-
"""Тексты главных страниц выборки калибровки -> drop KALIBR-TEKSTY.json (title, h1, 3000 знаков текста)."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
import analiz as A, obrabotka as O
V = json.load(open(os.path.join(D, 'kalibr_vyborka.json'), encoding='utf-8'))
def one(v):
    d = O.norm_domain(v['domain'])
    st, fin, doc = A.get('https://' + d + '/')
    if not st or st >= 400:
        st, fin, doc = A.get('http://' + d + '/')
    if not st or st >= 400:
        return dict(v, text='', ok=0)
    t, h1, vis = A.razbor(doc)
    return dict(v, title=t, h1=h1, text=vis[:3000], ok=1)
with ThreadPoolExecutor(12) as ex:
    res = list(ex.map(one, V))
json.dump(res, open(os.path.join(A.DROP, 'KALIBR-TEKSTY.json'), 'w', encoding='utf-8'), ensure_ascii=False)
print('===ИТОГ===', len(res), sum(r['ok'] for r in res))
