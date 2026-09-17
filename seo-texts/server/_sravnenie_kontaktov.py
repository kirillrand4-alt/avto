# -*- coding: utf-8 -*-
"""Наша контактная база против счётчиков платной витрины."""
import json, sqlite3

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=40)
o = {}
o['компаний'] = c.execute('select count(*) from companies').fetchone()[0]
o['адресов'] = c.execute('select count(*) from emails').fetchone()[0]
o['компаний_с_адресом'] = c.execute('select count(distinct inn) from emails').fetchone()[0]
o['телефонов'] = c.execute('select count(*) from phone_contacts').fetchone()[0]
o['компаний_с_телефоном'] = c.execute('select count(distinct inn) from phone_contacts').fetchone()[0]
try:
    o['контактов_с_ФИО'] = c.execute(
        "select count(*) from phone_contacts where coalesce(name,'')<>''").fetchone()[0]
except Exception as e:
    o['контактов_с_ФИО'] = repr(e)[:60]
try:
    o['адресов_с_ролью'] = c.execute(
        "select count(*) from emails where coalesce(role,'')<>''").fetchone()[0]
    o['роли_топ'] = c.execute(
        "select role, count(*) from emails where coalesce(role,'')<>'' "
        'group by 1 order by 2 desc limit 6').fetchall()
except Exception as e:
    o['адресов_с_ролью'] = repr(e)[:60]
o['компаний_хоть_с_чем_то'] = c.execute(
    'select count(*) from (select inn from emails union select inn from phone_contacts)'
).fetchone()[0]
c.close()

их = {'проектов': 204200, 'компаний': 161376, 'контактных_лиц': 427574}
o['витрина_investprojects'] = их
o['сравнение'] = {
    'лиц_на_компанию_у_них': round(их['контактных_лиц'] / их['компаний'], 2),
    'адресов_на_компанию_у_нас': round(o['адресов'] / max(o['компаний_с_адресом'], 1), 2),
    'покрытие_компаний_у_нас_%': round(100.0 * o['компаний_хоть_с_чем_то'] / max(o['компаний'], 1), 1),
}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1, default=str)[:4000])
