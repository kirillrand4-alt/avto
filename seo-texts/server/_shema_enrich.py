# -*- coding: utf-8 -*-
"""Что вообще есть в карточке: таблицы enrich.db и заполненность колонок companies."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
итог = {'таблицы': {}}
for (т,) in c.execute("select name from sqlite_master where type='table' order by name"):
    try:
        итог['таблицы'][т] = c.execute('select count(*) from %s' % т).fetchone()[0]
    except Exception:
        pass
колонки = [r[1] for r in c.execute('pragma table_info(companies)')]
итог['companies_колонки'] = колонки
всего = c.execute('select count(*) from companies').fetchone()[0]
итог['компаний'] = всего
зап = {}
for k in колонки:
    try:
        зап[k] = c.execute("select count(*) from companies where coalesce(%s,'')<>''" % k).fetchone()[0]
    except Exception:
        pass
итог['заполнено'] = dict(sorted(зап.items(), key=lambda x: -x[1]))
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
