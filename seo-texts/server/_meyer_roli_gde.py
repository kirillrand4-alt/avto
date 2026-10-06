# -*- coding: utf-8 -*-
"""Где в базах лежат роли/должности, сколько их по 27 201 ИНН базы Meyer."""
import glob, io, json, os, sqlite3
инн = [s.strip() for s in io.open(r'C:\seostat\drop\drop-storage\meyer-27201-inn.txt', encoding='utf-8') if s.strip()]
o = {}
for бд in (r'C:\sender\enrich.db', r'C:\sender\obzvon-index.db', r'C:\sender\tehlpr.db'):
    c = sqlite3.connect('file:%s?mode=ro' % бд, uri=True, timeout=60)
    c.execute('create temp table t(inn text primary key)')
    c.executemany('insert or ignore into t values (?)', [(i,) for i in инн])
    for т, in c.execute("select name from sqlite_master where type='table'"):
        кол = [r[1] for r in c.execute('pragma table_info("%s")' % т)]
        роль = [к for к in кол if any(w in к.lower() for w in ('rol', 'post', 'dolzh', 'person', 'fio', 'klass', 'class'))]
        if not роль:
            continue
        з = {'колонки_ролей': роль, 'строк_всего': c.execute('select count(*) from "%s"' % т).fetchone()[0]}
        if 'inn' in кол:
            з['строк_по_27201'] = c.execute('select count(*) from "%s" x join t on t.inn=x.inn' % т).fetchone()[0]
            з['компаний_по_27201'] = c.execute('select count(distinct x.inn) from "%s" x join t on t.inn=x.inn' % т).fetchone()[0]
            к0 = роль[0]
            з['непустых_%s' % к0] = c.execute("select count(*) from \"%s\" x join t on t.inn=x.inn where coalesce(x.\"%s\",'')<>''" % (т, к0)).fetchone()[0]
        з['пример'] = [[str(v)[:40] for v in r] for r in c.execute('select %s from "%s" limit 2' % (','.join('"%s"' % к for к in роль[:4]), т))]
        o[os.path.basename(бд) + ':' + т] = з
    c.close()
print('===ИТОГ===')
for к, v in o.items():
    print(к, json.dumps(v, ensure_ascii=False)[:600])
