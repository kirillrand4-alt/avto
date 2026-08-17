# -*- coding: utf-8 -*-
"""Что за «прочие источники» у имён: 4512 записей — чей это домен на самом деле."""
import json
import sqlite3
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender\server')
import ploshchadki as PL          # noqa: E402
import karantin_kesha as KK       # noqa: E402

e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
e.row_factory = sqlite3.Row
сайты = {str(r[0]): PL.домен(r[1] or '') for r in e.execute(
    "select inn, coalesce(nullif(site,''),nullif(cand_site,''),'') from companies")}
# домены почтовых адресов компании — ещё один способ узнать её собственный сайт
почтовые = {}
for r in e.execute("select inn, email from emails where coalesce(email,'')<>''"):
    д = (r['email'].split('@')[-1] or '').lower()
    почтовые.setdefault(str(r['inn']), set()).add(д)

итог = {'прочих': 0, 'на_деле_свой_домен_зеркало': 0, 'домен_почты_компании': 0,
        'соцсети_и_каталоги': 0, 'настоящее_прочее': 0}
домены = Counter()
компаний_свой = set()
примеры = []
for r in e.execute("select inn, person, post, coalesce(source,'') ист, "
                   "coalesce(source_url,'') url from people "
                   "where coalesce(person,'')<>'' and coalesce(post,'')<>'' "
                   "and coalesce(source_url,'')<>''"):
    inn = str(r['inn'])
    дом = PL.домен(r['url'])
    свой = сайты.get(inn, '')
    if свой and (дом == свой or дом.endswith('.' + свой) or свой.endswith('.' + дом)):
        компаний_свой.add(inn)
        continue
    if 'nalog.ru' in дом or 'egrul' in r['url']:
        continue
    итог['прочих'] += 1
    домены[дом] += 1
    if свой and KK._почти_тот_же(дом, свой):
        итог['на_деле_свой_домен_зеркало'] += 1
        компаний_свой.add(inn)
        if len(примеры) < 5:
            примеры.append({'инн': inn, 'имя': r['person'][:30], 'ссылка': дом,
                            'сайт_в_базе': свой, 'вывод': 'зеркало домена'})
    elif дом in (почтовые.get(inn) or set()):
        итог['домен_почты_компании'] += 1
        компаний_свой.add(inn)
        if len(примеры) < 10:
            примеры.append({'инн': inn, 'имя': r['person'][:30], 'ссылка': дом,
                            'сайт_в_базе': свой or '(нет)', 'вывод': 'домен её почты'})
    elif PL.из_списка(дом):
        итог['соцсети_и_каталоги'] += 1
    else:
        итог['настоящее_прочее'] += 1
e.close()
итог['компаний_с_именем_со_своего_домена'] = len(компаний_свой)
итог['верх_доменов_прочего'] = домены.most_common(12)
итог['примеры'] = примеры
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
