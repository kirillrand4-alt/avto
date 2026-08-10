# -*- coding: utf-8 -*-
"""Ищем ИСХОДНУЮ базу atlas_copco.db на сервере: нет ли в ней адреса, который потерялся.

442 факта пришли из неё БЕЗ ссылки. Прежде чем добывать ссылки заново поиском (первый
заход дал 0 из 120 — искал в ЕИС, а закупки Норникеля идут через tender.pro), надо
проверить дешёвое: может, адрес там был и просто не перенёсся при вливании.
"""
import json, os, sqlite3

najd = []
for koren in (r'C:\sender', r'C:\seostat', r'C:\seostat\data'):
    if not os.path.isdir(koren):
        continue
    for x in os.listdir(koren):
        if 'atlas' in x.lower():
            najd.append(os.path.join(koren, x))
o = {'najdeno': najd}
for put in najd:
    if not put.endswith('.db'):
        continue
    try:
        p = sqlite3.connect('file:%s?mode=ro' % put, uri=True)
        tabl = [r[0] for r in p.execute("select name from sqlite_master where type='table'")]
        o[put] = {'tablicy': tabl}
        for t in tabl:
            kol = [r[1] for r in p.execute('pragma table_info(%s)' % t)]
            n = p.execute('select count(*) from %s' % t).fetchone()[0]
            o[put][t] = {'strok': n, 'kolonki': kol}
            urlk = [k for k in kol if 'url' in k.lower() or 'ssyl' in k.lower() or 'link' in k.lower()]
            if urlk and n:
                k = urlk[0]
                o[put][t]['s_adresom'] = p.execute(
                    "select count(*) from %s where coalesce(%s,'') like 'http%%'" % (t, k)).fetchone()[0]
                o[put][t]['primer'] = p.execute(
                    "select %s from %s where coalesce(%s,'') like 'http%%' limit 2" % (k, t, k)).fetchall()
        p.close()
    except Exception as e:
        o[put] = {'oshibka': str(e)[:150]}
print(json.dumps(o, ensure_ascii=False, indent=1))
