# -*- coding: utf-8 -*-
"""С сайта компании имя или из реестра — для приветствия это разные вещи."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender\server')
import ploshchadki as PL  # noqa: E402

e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
e.row_factory = sqlite3.Row
сайты = {str(r[0]): PL.домен(r[1] or '') for r in e.execute(
    "select inn, coalesce(nullif(site,''),nullif(cand_site,''),'') from companies")}
итог = {'с_доказательством': 0, 'ссылка_на_свой_сайт': 0, 'ссылка_на_реестр': 0,
        'ссылка_на_прочее': 0}
компаний_свой = set()
примеры = {'свой сайт': [], 'реестр': [], 'прочее': []}
for r in e.execute("select inn, person, post, coalesce(source,'') istochnik, "
                   "coalesce(source_url,'') url from people "
                   "where coalesce(person,'')<>'' and coalesce(post,'')<>'' "
                   "and coalesce(source_url,'')<>''"):
    итог['с_доказательством'] += 1
    дом = PL.домен(r['url'])
    свой = сайты.get(str(r['inn']), '')
    if свой and (дом == свой or дом.endswith('.' + свой) or свой.endswith('.' + дом)):
        ключ, поле = 'свой сайт', 'ссылка_на_свой_сайт'
        компаний_свой.add(str(r['inn']))
    elif 'nalog.ru' in дом or 'egrul' in r['url'] or PL.из_списка(r['url']):
        ключ, поле = 'реестр', 'ссылка_на_реестр'
    else:
        ключ, поле = 'прочее', 'ссылка_на_прочее'
    итог[поле] += 1
    if len(примеры[ключ]) < 3:
        примеры[ключ].append({'инн': str(r['inn']), 'имя': r['person'][:35],
                              'должность': r['post'][:30], 'откуда': r['url'][:55]})
итог['компаний_с_именем_со_своего_сайта'] = len(компаний_свой)
итог['примеры'] = примеры
e.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2600])
