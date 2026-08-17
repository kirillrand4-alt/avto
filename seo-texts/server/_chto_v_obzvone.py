# -*- coding: utf-8 -*-
"""Что есть в базе обзвона и чего из этого нет у нас в companies."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
o = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/obzvon-index.db', uri=True)
колонки = [r[1] for r in o.execute('pragma table_info(obzvon)')]
всего = o.execute('select count(*) from obzvon').fetchone()[0]
зап = {}
for k in колонки:
    try:
        зап[k] = o.execute("select count(*) from obzvon where coalesce(%s,'')<>''" % k).fetchone()[0]
    except Exception:
        pass
примеры = [dict(r) for r in o.execute(
    'select * from obzvon limit 2')] if False else []
o.row_factory = sqlite3.Row
одна = dict(o.execute('select * from obzvon limit 1').fetchone())
o.close()

e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
наши = {str(r[0]) for r in e.execute('select inn from companies')}
без_выручки = {str(r[0]) for r in e.execute(
    "select inn from companies where coalesce(revenue_rub,'')='' or revenue_rub=0")}
e.close()

o = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/obzvon-index.db', uri=True)
есть_выручка = 0
проверено = 0
сп = list(без_выручки)
for i in range(0, len(сп), 400):
    часть = сп[i:i+400]
    q = ','.join('?' * len(часть))
    for inn, rev in o.execute(
            "select inn, coalesce(revenue,'') from obzvon where inn in (%s)" % q, часть):
        проверено += 1
        if str(rev).strip():
            есть_выручка += 1
o.close()

print(json.dumps({'строк_в_обзвоне': всего, 'заполненность': dict(sorted(зап.items(), key=lambda x: -x[1])),
                  'пример_строки': {k: (str(v)[:40] if v is not None else None) for k, v in одна.items()},
                  'у_нас_без_выручки': len(без_выручки),
                  'из_них_есть_в_обзвоне': проверено,
                  'из_них_выручка_заполнена': есть_выручка}, ensure_ascii=False, indent=1)[:3000])
