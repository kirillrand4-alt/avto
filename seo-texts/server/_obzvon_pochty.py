# -*- coding: utf-8 -*-
r"""Есть ли почты в базе обзвона у паспортных компаний без адреса в обогащении."""
import json
import sqlite3

o = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=60)
d = {'таблицы': [r[0] for r in o.execute(
    "select name from sqlite_master where type='table'")]}
таб = 'obzvon' if 'obzvon' in d['таблицы'] else (d['таблицы'][0] if d['таблицы'] else '')
d['таблица'] = таб
if таб:
    d['колонки'] = [x[1] for x in o.execute('PRAGMA table_info(%s)' % таб)]
    поле = next((k for k in d['колонки'] if k.lower() in
                 ('emails_base', 'emails_site', 'email', 'mail')), '')
    d['поле_почты'] = поле
    d['строк'] = o.execute('select count(*) from %s' % таб).fetchone()[0]
    if поле:
        for пп in ('emails_base', 'emails_site'):
            if пп in d['колонки']:
                d['с_почтой_' + пп] = o.execute(
                    "select count(*) from %s where coalesce(%s,'') not in ('','[]')"
                    % (таб, пп)).fetchone()[0]
o.close()

e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
полные = {str(r[0]) for r in e.execute(
    "select inn from site_facts where coalesce(format,0)>=2 "
    "and facts_json like '%\"продукция\": [\"%'")}
есть_адрес = {str(r[0]) for r in e.execute('select distinct inn from emails')}
e.close()
d['полных_паспортов'] = len(полные)
d['из_них_без_адреса_в_обогащении'] = len(полные - есть_адрес)

if таб and d.get('поле_почты'):
    o = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=60)
    инн_поле = next((k for k in d['колонки'] if k.lower() == 'inn'), 'inn')
    найдено = 0
    для_них = полные - есть_адрес
    примеры = []
    for инн, б, с in o.execute(
            "select %s, coalesce(emails_base,''), coalesce(emails_site,'') "
            'from %s' % (инн_поле, таб)):
        if str(инн) not in для_них:
            continue
        если = (str(б).strip(' []') or str(с).strip(' []'))
        if если:
            найдено += 1
            if len(примеры) < 5:
                примеры.append({'инн': str(инн), 'почты': если[:70]})
    d['примеры'] = примеры
    o.close()
    d['из_безадресных_нашлись_в_обзвоне'] = найдено
print(json.dumps(d, ensure_ascii=False, indent=1)[:2000])
