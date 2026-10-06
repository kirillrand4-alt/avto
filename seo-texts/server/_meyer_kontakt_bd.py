# -*- coding: utf-8 -*-
"""Найти базы сессий с таблицей контактов с должностями (kontakt/dolzhnost/rang), сколько по 27 201 ИНН."""
import glob, io, json, os, sqlite3
инн = [s.strip() for s in io.open(r'C:\seostat\drop\drop-storage\meyer-27201-inn.txt', encoding='utf-8') if s.strip()]
бд = set()
for маска in (r'C:\sender\*.db', r'C:\sender\*\*.db', r'C:\sender\*\*\*.db', r'C:\seostat\*.db', r'C:\seostat\*\*.db',
              r'C:\seostat\*\*\*.db'):
    бд |= set(glob.glob(маска))
o = {'баз': len(бд)}
for п in sorted(бд):
    if any(x in п.lower() for x in ('backup', '_tmp', 'pered', '.bak')) or os.path.getsize(п) > 4e9:
        continue
    try:
        c = sqlite3.connect('file:%s?mode=ro' % п, uri=True, timeout=20)
        for т, in c.execute("select name from sqlite_master where type='table'"):
            кол = [r[1] for r in c.execute('pragma table_info("%s")' % т)]
            if not any(к.lower() in ('dolzhnost', 'post', 'rol', 'role', 'rang') for к in кол):
                continue
            if п.endswith(('enrich.db', 'tehlpr.db')):
                continue
            з = {'колонки': кол[:25], 'строк': c.execute('select count(*) from "%s"' % т).fetchone()[0],
                 'МБ_файла': round(os.path.getsize(п) / 1e6)}
            ик = next((к for к in кол if к.lower() in ('inn', 'инн')), None)
            if ик:
                c.execute('create temp table if not exists t(inn text primary key)')
                if not c.execute('select count(*) from t').fetchone()[0]:
                    c.executemany('insert or ignore into t values (?)', [(i,) for i in инн])
                з['строк_по_27201'] = c.execute('select count(*) from "%s" x join t on t.inn=x."%s"' % (т, ик)).fetchone()[0]
                з['компаний_по_27201'] = c.execute('select count(distinct x."%s") from "%s" x join t on t.inn=x."%s"' % (ик, т, ик)).fetchone()[0]
            o['%s :: %s' % (п, т)] = з
        c.close()
    except sqlite3.Error as e:
        o.setdefault('ошибки', []).append([п, str(e)[:60]])
print('===ИТОГ===')
for к, v in o.items():
    print(к, json.dumps(v, ensure_ascii=False)[:700])
