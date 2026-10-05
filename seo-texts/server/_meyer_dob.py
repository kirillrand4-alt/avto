# -*- coding: utf-8 -*-
"""Как в базе записаны добавочные номера: колонки, форматы, сколько их у ролевых контактов."""
import json
import sqlite3

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=60)
o = {}
for т in ('phone_contacts', 'people', 'imena'):
    o[т + '_cols'] = [r[1] for r in c.execute('pragma table_info(%s)' % т)]
ДОБ = "(phone like '%доб%' or phone like '%доп%' or phone like '%ext%' or phone like '%вн.%' " \
      "or phone like '%#%' or length(replace(replace(replace(replace(replace(replace(phone,' ',''),'-',''),"\
      "'(',''),')',''),'+',''),'.',''))>11)"
o['pc_доб_всего'] = c.execute('select count(*), count(distinct inn) from phone_contacts where ' + ДОБ).fetchone()
o['pc_доб_с_ролью'] = c.execute("select count(*), count(distinct inn) from phone_contacts where "
                                "(coalesce(role,'')<>'' or coalesce(person,'')<>'') and " + ДОБ).fetchone()
o['pc_доб_примеры'] = [list(r) for r in c.execute(
    "select phone, person, role, source from phone_contacts where (coalesce(role,'')<>'' or "
    "coalesce(person,'')<>'') and " + ДОБ + ' limit 25')]
o['pc_доб_примеры_все'] = [r[0] for r in c.execute('select phone from phone_contacts where ' + ДОБ + ' limit 15')]
o['people_доб'] = c.execute('select count(*) from people where ' + ДОБ).fetchone()
o['people_доб_примеры'] = [list(r) for r in c.execute(
    'select phone, person, post, source from people where ' + ДОБ + ' limit 10')]
o['people_с_тел'] = c.execute("select count(*), count(distinct inn) from people where coalesce(phone,'')<>''").fetchone()
o['people_тел_примеры'] = [list(r) for r in c.execute(
    "select phone, person, post, source from people where coalesce(phone,'')<>'' limit 8")]
c.close()
print('===ИТОГ===')
for к, v in o.items():
    print(к, json.dumps(v, ensure_ascii=False, default=str)[:2500])
