# -*- coding: utf-8 -*-
"""Сколько почт во ВСЕЙ базе: наши собранные + обе колонки обзвона."""
import json
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
итог['enrich_emails_строк'] = e.execute('select count(*) from emails').fetchone()[0]
итог['enrich_уникальных'] = e.execute(
    'select count(distinct lower(email)) from emails').fetchone()[0]
e.close()
o = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/obzvon-index.db', uri=True)
всего, уникальные, по_колонкам = 0, set(), {'emails_base': 0, 'emails_site': 0}
for base, site in o.execute("select coalesce(emails_base,''), coalesce(emails_site,'') "
                            'from obzvon'):
    for имя, значение in (('emails_base', base), ('emails_site', site)):
        найдено = re.findall(r'[\w.+-]+@[\w.-]+\.[a-zA-Zрф]{2,}', значение or '')
        по_колонкам[имя] += len(найдено)
        всего += len(найдено)
        уникальные.update(x.lower() for x in найдено)
o.close()
итог['обзвон_по_колонкам'] = по_колонкам
итог['обзвон_всего_вхождений'] = всего
итог['обзвон_уникальных'] = len(уникальные)
итог['итого_уникальных_примерно'] = len(уникальные) + итог['enrich_уникальных']
print(json.dumps(итог, ensure_ascii=False, indent=1))
