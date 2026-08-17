# -*- coding: utf-8 -*-
"""Скольким получателям панели мы можем дать НАДЁЖНОЕ имя из своей базы.

Панель считает имя надёжным, когда есть contact_name, сайт свой и есть ссылка-
доказательство. Первое и третье у нас лежат в people, второе — улика привязки.
"""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender\server')
import sverka_privyazki as SP  # noqa: E402

s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
получатели = list(s.execute(
    "select id, coalesce(inn,'') inn, coalesce(email,'') email, "
    "coalesce(contact_name,'') imya, coalesce(source,'') partiya from recipients "
    "where coalesce(inn,'')<>''"))
s.close()

e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
e.row_factory = sqlite3.Row
люди = {}
for r in e.execute("select inn, person, post, coalesce(role,'') role, "
                   "coalesce(source_url,'') url from people "
                   "where coalesce(person,'')<>'' and coalesce(post,'')<>'' "
                   "and coalesce(source_url,'')<>''"):
    люди.setdefault(str(r['inn']), []).append(dict(r))
компании = {str(r['inn']): dict(r) for r in e.execute(
    "select inn, coalesce(name,'') name, coalesce(ogrn,'') ogrn, "
    "coalesce(nullif(site,''),nullif(cand_site,''),'') site from companies")}
e.close()

итог = {'получателей_с_инн': len(получатели), 'имя_в_панели_уже_есть': 0,
        'можем_дать_имя': 0, 'имя_есть_и_привязка_доказана': 0, 'нечего_дать': 0}
примеры = []
for r in получатели:
    if r['imya']:
        итог['имя_в_панели_уже_есть'] += 1
        continue
    сп = люди.get(r['inn'])
    if not сп:
        итог['нечего_дать'] += 1
        continue
    итог['можем_дать_имя'] += 1
    k = компании.get(r['inn']) or {}
    улики, _ = SP.улики(r['inn'], k.get('name', ''), k.get('site', ''), k.get('ogrn', ''))
    if улики:
        итог['имя_есть_и_привязка_доказана'] += 1
        if len(примеры) < 5:
            примеры.append({'инн': r['inn'], 'почта': r['email'],
                            'имя': сп[0]['person'], 'должность': сп[0]['post'][:40],
                            'ссылка': сп[0]['url'][:60], 'улики': '+'.join(улики)})
итог['примеры'] = примеры
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2500])
