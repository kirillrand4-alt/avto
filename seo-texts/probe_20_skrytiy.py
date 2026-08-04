# -*- coding: utf-8 -*-
"""Отдать 2-й сессии 20 своих скрытий на проверку — обмен симметричный, моя половина за мной.

ЗАЧЕМ ИМЕННО ТАК. Они проверили мою чистку на 190 строках и нашли, что отсев «трубопровод»
режет около 8 % живого. Я обещала встречные 20 и не отдала. Беру НЕ случайные, а самые
спорные: те, где скрытие поставлено моим правилом, а рядом у того же предприятия есть факт,
который правилу противоречит. Случайная выборка проверила бы лёгкие случаи; спорные — те, на
которых правило и ломается.
"""
import csv
import io
import json
import os
import re
import sqlite3
import urllib.request

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
MOI = "coalesce(reason,'') like '%3-я сессия%' or coalesce(reason,'') like '%3-й сессии%' " \
      "or coalesce(reason,'') like '%musor_faktov%'"
stroki = sale.execute(
    f"select inn, kind, coalesce(value,''), coalesce(reason,''), coalesce(created_at,'') "
    f"from hidden_item where {MOI}").fetchall()
print('моих скрытий по подписи в причине:', len(stroki))

NASH = re.compile(r'центробежн|турбокомпрессор|турбовоздуходувк|нагнетател|воздуходувк', re.I)
spornye = []
for inn, kind, val, reason, kogda in stroki:
    if kind != 'fact' or not val.isdigit():
        continue
    r = sale.execute("select coalesce(quote,''), coalesce(equipment_type,''), "
                     "coalesce(source,'') from f.fact where id = ?", (val,)).fetchone()
    if not r:
        continue
    quote, tip, src = r
    # Спорное: я скрыла, а слово нашей машины в цитате есть, либо разметка говорит центробежная.
    if NASH.search(quote) or 'центробежн' in tip.lower():
        spornye.append({'inn': inn, 'id_fakta': val, 'prichina_skrytiya': reason[:150],
                        'equipment_type': tip, 'istochnik': src, 'citata': quote[:250],
                        'vopros': 'скрыто мной, но в цитате есть слово нашей машины — верно ли'})
    if len(spornye) >= 20:
        break
print('спорных отобрано:', len(spornye))
if spornye:
    b = io.StringIO()
    w = csv.DictWriter(b, fieldnames=list(spornye[0]), delimiter=';')
    w.writeheader()
    w.writerows(spornye)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/DLYA-2S-20-moih-skrytiy-na-proverku.csv', data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    with urllib.request.urlopen(req, timeout=120) as r:
        print('выгружено:', r.status, len(telo), 'байт')
    for z in spornye[:5]:
        print(' ', z['inn'], '|', z['citata'][:100])
