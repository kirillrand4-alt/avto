# -*- coding: utf-8 -*-
"""Исходные строки по 27 201 компании базы Meyer — ВСЕ колонки: obzvon (база обзвона)
и companies (enrich.db). ИНН — из meyer-27201-inn.txt на дропе. CSV (;, UTF-8 BOM) на дроп."""
import csv, io, json, os, shutil, sqlite3
ДРОП = r'C:\seostat\drop\drop-storage'
инн = [s.strip() for s in io.open(os.path.join(ДРОП, 'meyer-27201-inn.txt'), encoding='utf-8') if s.strip()]
o = {'инн': len(инн)}
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
c.execute('create temp table t(inn text primary key)')
c.executemany('insert or ignore into t values (?)', [(i,) for i in инн])
for имя, sql, табл in (
        ('meyer-ishodnaya-obzvon-0610.csv', 'select o.* from obz.obzvon o join t on t.inn=o.inn', 'obz.obzvon'),
        ('meyer-ishodnaya-companies-0610.csv', 'select c.* from companies c join t on t.inn=c.inn', 'companies')):
    cur = c.execute(sql)
    кол = [d[0] for d in cur.description]
    п = os.path.join(r'C:\sender\server', имя)
    n = 0
    with io.open(п, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(кол)
        for r in cur:
            w.writerow(['' if v is None else v for v in r])
            n += 1
        f.flush(); os.fsync(f.fileno())
    shutil.copyfile(п, os.path.join(ДРОП, имя))
    o[имя] = {'строк': n, 'колонок': len(кол), 'МБ': round(os.path.getsize(п) / 1e6, 1), 'колонки': кол}
o['нет_в_obzvon'] = c.execute('select count(*) from t where inn not in (select inn from obz.obzvon)').fetchone()[0]
o['нет_в_companies'] = c.execute('select count(*) from t where inn not in (select inn from companies)').fetchone()[0]
o['дублей_в_obzvon'] = c.execute('select count(*) from (select o.inn from obz.obzvon o join t on t.inn=o.inn group by o.inn having count(*)>1)').fetchone()[0]
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False))
