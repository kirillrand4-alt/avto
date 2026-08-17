# -*- coding: utf-8 -*-
"""Имена из реестров: сколько компаний и людей дают Ростехнадзор, закупки, тендеры."""
import json
import sqlite3
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender\server')
import ploshchadki as PL  # noqa: E402

ГРУППЫ = (('Ростехнадзор', ('gosnadzor.ru',)),
          ('госзакупки', ('zakupki.gov.ru', 'torgi.gov.ru')),
          ('тендерные площадки', ('tender.pro', 'rts-tender', 'b2b-center', 'etp')),
          ('соцсети', ('vk.com', 'ok.ru', 't.me', 'facebook')),
          ('реестр ЕГРЮЛ', ('nalog.ru',)))
e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
e.row_factory = sqlite3.Row
люди = defaultdict(lambda: {'записей': 0, 'компаний': set(), 'с_должностью': 0})
прочее = defaultdict(int)
for r in e.execute("select inn, person, coalesce(post,'') post, coalesce(source_url,'') url "
                   "from people where coalesce(person,'')<>'' and coalesce(source_url,'')<>''"):
    дом = PL.домен(r['url'])
    имя = None
    for г, куски in ГРУППЫ:
        if any(k in дом for k in куски):
            имя = г
            break
    if имя is None:
        прочее[дом] += 1
        continue
    б = люди[имя]
    б['записей'] += 1
    б['компаний'].add(str(r['inn']))
    б['с_должностью'] += 1 if r['post'] else 0
e.close()
итог = {г: {'записей': б['записей'], 'компаний': len(б['компаний']),
            'с_должностью': б['с_должностью']} for г, б in люди.items()}
print(json.dumps({'по_источникам': итог,
                  'остальные_домены_верх': sorted(прочее.items(), key=lambda x: -x[1])[:10]},
                 ensure_ascii=False, indent=1)[:2500])
