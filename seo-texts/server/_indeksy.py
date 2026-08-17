# -*- coding: utf-8 -*-
"""Есть ли индексы по inn у таблиц, к которым я лезу подзапросом на каждую строку."""
import json, sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
итог = {}
for т in ('people', 'phone_contacts', 'companies', 'site_facts'):
    итог[т] = {'строк': c.execute('select count(*) from %s' % т).fetchone()[0],
               'индексы': [r[1] for r in c.execute('pragma index_list(%s)' % т)]}
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
