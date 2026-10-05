# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=60)
o = {}
for т in ('companies','emails','phone_contacts','people','site_facts','imena','roli_sud','email_sources'):
    try:
        o[т] = {'к': [r[1] for r in c.execute('pragma table_info(%s)' % т)],
                'n': c.execute('select count(*) from %s' % т).fetchone()[0]}
    except Exception as e:
        o[т] = repr(e)[:60]
try:
    o['people_пример'] = c.execute('select * from people limit 2').fetchall()
except Exception as e:
    o['people_пример'] = repr(e)[:60]
o['роли_телефонов'] = c.execute(
    "select coalesce(role,''), count(*) from phone_contacts group by 1 order by 2 desc limit 12").fetchall()
o['телефоны_с_ФИО'] = c.execute(
    "select count(*) from phone_contacts where coalesce(person,'')<>''").fetchone()[0]
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, default=str)[:5000])
