# -*- coding: utf-8 -*-
"""Где лежат номера/компании из файлов другой сессии, которых нет в моей выгрузке."""
import glob
import json
import os
import sqlite3

ИНН = ['7806191794', '1106018296', '5829002496', '4345000224', '9102256223', '6603025045', '5452114972']
ТЕЛ = ['9787305959', '9623893888', '9621342433', '2289080', '9262225727', '9319671007', '9128262059']
ФИО = ['Прилуцкий', 'Малышев Дмитрий', 'Казанский Андрей', 'Ерофеев Андрей']
o = {}
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=60)
c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
тт = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
o['таблицы'] = тт
for и in ИНН[:4]:
    o['комп_' + и] = c.execute(
        'select name, okved, substr(okved_all,1,120), is_competitor, status_egrul, division from companies '
        'where inn=?', (и,)).fetchall()
    o['обз_' + и] = c.execute('select division, okved_main, substr(okved_all_codes,1,80), status from obz.obzvon '
                              'where inn=?', (и,)).fetchall()
# в каких таблицах встречаются ИНН и номера
нашлось = {}
for т in тт:
    cols = [r[1] for r in c.execute('pragma table_info("%s")' % т)]
    if 'inn' in cols:
        n = c.execute('select count(*) from "%s" where inn in (%s)' % (т, ','.join('?' * len(ИНН))), ИНН).fetchone()[0]
        if n:
            нашлось.setdefault(т, {})['инн'] = n
    текст = [к for к in cols if к in ('phone', 'phones', 'telefon', 'person', 'fio', 'detail', 'data', 'json',
                                      'raw', 'citata', 'text', 'kontakt', 'kontakty')]
    for к in текст:
        for t in ТЕЛ + ФИО:
            try:
                n = c.execute('select count(*) from "%s" where "%s" like ?' % (т, к), ('%' + t + '%',)).fetchone()[0]
            except sqlite3.Error:
                n = 0
            if n:
                нашлось.setdefault(т, {}).setdefault(к, []).append(t)
o['нашлось_enrich'] = нашлось
c.close()
# другие базы на сервере
бд = []
for маска in (r'C:\sender\*.db', r'C:\sender\**\*.db', r'C:\seostat\**\*.db', r'C:\sender\**\*vitrin*',
              r'C:\seostat\**\*vitrin*', r'C:\sender\**\*lpr*'):
    бд += glob.glob(маска, recursive=True)
бд = sorted(set(бд))
o['файлы'] = [(п, round(os.path.getsize(п) / 1e6, 1)) for п in бд][:60]
for п in бд:
    if not п.endswith('.db') or 'enrich.db' in п or 'obzvon-index' in п or os.path.getsize(п) > 3e9:
        continue
    try:
        cc = sqlite3.connect('file:%s?mode=ro' % п, uri=True, timeout=10)
        for т, in cc.execute("select name from sqlite_master where type='table'"):
            cols = [r[1] for r in cc.execute('pragma table_info("%s")' % т)]
            for к in cols:
                for t in ['9787305959', 'Прилуцкий', '2289080']:
                    try:
                        n = cc.execute('select count(*) from "%s" where cast("%s" as text) like ?' % (т, к),
                                       ('%' + t + '%',)).fetchone()[0]
                    except sqlite3.Error:
                        n = 0
                    if n:
                        o.setdefault('нашлось_другие', []).append([п, т, к, t, n])
        cc.close()
    except sqlite3.Error as e:
        o.setdefault('ошибки', []).append([п, str(e)[:60]])
print('===ИТОГ===')
for к, v in o.items():
    print(к, json.dumps(v, ensure_ascii=False, default=str)[:3000])
