# -*- coding: utf-8 -*-
"""tehlpr.db (витрина ЛПР) и почему компаний второго файла нет в моей базе."""
import json
import sqlite3

o = {}
t = sqlite3.connect(r'file:C:\sender\tehlpr.db?mode=ro', uri=True, timeout=60)
for имя, in t.execute("select name from sqlite_master where type='table'"):
    o['tehlpr:' + имя] = {'колонки': [r[1] for r in t.execute('pragma table_info("%s")' % имя)],
                          'строк': t.execute('select count(*) from "%s"' % имя).fetchone()[0]}
o['tehlpr_пример'] = [[str(v)[:80] for v in r] for r in t.execute(
    "select * from tehlpr where person like '%Прилуцкий%' or person like '%Казанский%' limit 3")]
t.close()

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=60)
c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
for и in ['7806191794', '1106018296', '5829002496', '4345000224', '5452114972', '6679096134', '2308001057']:
    o['комп_' + и] = [c.execute('select name, okved, substr(okved_all,1,150), is_competitor, status_egrul, division '
                                'from companies where inn=?', (и,)).fetchall(),
                      c.execute('select division, okved_main, substr(okved_all_codes,1,100), status '
                                'from obz.obzvon where inn=?', (и,)).fetchall()]
o['таблицы_enrich'] = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
c.close()
print('===ИТОГ===')
for к, v in o.items():
    print(к, json.dumps(v, ensure_ascii=False, default=str)[:1500])
