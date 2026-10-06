# -*- coding: utf-8 -*-
"""Исходные таблицы КОНТАКТОВ (все колонки) по 27 201 ИНН базы Meyer: phone_contacts,
emails, people, imena, tehlpr. CSV (;, UTF-8 BOM) на дроп."""
import csv, io, json, os, shutil, sqlite3
ДРОП = r'C:\seostat\drop\drop-storage'
инн = [s.strip() for s in io.open(os.path.join(ДРОП, 'meyer-27201-inn.txt'), encoding='utf-8') if s.strip()]
o = {}
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
c.execute(r"attach database 'file:C:\sender\tehlpr.db?mode=ro' as th")
c.execute('create temp table t(inn text primary key)')
c.executemany('insert or ignore into t values (?)', [(i,) for i in инн])
for табл, имя in (('phone_contacts', 'telefony'), ('emails', 'pochty'), ('people', 'lyudi'),
                  ('imena', 'imena'), ('th.tehlpr', 'tehlpr')):
    cur = c.execute('select x.* from %s x join t on t.inn=x.inn order by x.inn' % табл)
    кол = [d[0] for d in cur.description]
    файл = 'meyer-ishodnaya-%s-0610.csv' % имя
    п = os.path.join(r'C:\sender\server', файл)
    n = 0
    with io.open(п, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(кол)
        for r in cur:
            w.writerow(['' if v is None else v for v in r])
            n += 1
        f.flush(); os.fsync(f.fileno())
    shutil.copyfile(п, os.path.join(ДРОП, файл))
    роль = [к for к in кол if к in ('role', 'post', 'person')]
    з = {'строк': n, 'колонок': len(кол), 'МБ': round(os.path.getsize(п) / 1e6, 1), 'колонки': кол}
    for к in роль:
        з['непустых_' + к] = c.execute("select count(*) from %s x join t on t.inn=x.inn where coalesce(x.%s,'')<>''" % (табл, к)).fetchone()[0]
    o[файл] = з
c.close()
print('===ИТОГ===')
for к, v in o.items():
    print(к, json.dumps(v, ensure_ascii=False))
