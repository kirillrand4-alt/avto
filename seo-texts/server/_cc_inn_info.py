# -*- coding: utf-8 -*-
"""Сведения по ИНН из таблицы CC и с сайтов: название, ОКВЭД, регион, выручка, статус (наша база)."""
import io, json, os, shutil, sqlite3
инн = [s.strip() for s in io.open(r'C:\seostat\drop\drop-storage\cc-inn.txt', encoding='utf-8') if s.strip()]
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
c.execute('create temp table t(inn text primary key)')
c.executemany('insert or ignore into t values (?)', [(i,) for i in инн])
out = {}
for r in c.execute(
        "select t.inn, coalesce(nullif(c.name,''), o.name_short, ''), coalesce(nullif(c.okved,''), o.okved_main, ''), "
        "coalesce(c.okved_all,'')||' '||coalesce(o.okved_all_codes,''), coalesce(nullif(c.region,''), o.region, ''), "
        "case when coalesce(c.revenue_rub,0)>0 then c.revenue_rub else o.revenue_rub end, "
        "case when coalesce(c.revenue_rub,0)>0 then c.revenue_year else o.god_otch end, "
        "coalesce(nullif(c.status_egrul,''), o.status, ''), coalesce(c.is_competitor,0), coalesce(o.base_label, c.division, '') "
        'from t left join companies c on c.inn=t.inn left join obz.obzvon o on o.inn=t.inn'):
    if any(r[1:5]):
        out[r[0]] = {'название': r[1], 'оквэд': r[2], 'оквэд_все': r[3].strip(), 'регион': r[4],
                     'выручка': r[5], 'год': r[6], 'статус': r[7], 'конкурент': r[8], 'база': r[9]}
c.close()
п = r'C:\sender\server\cc-inn-info.json'
with io.open(п, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, default=str)
    f.flush(); os.fsync(f.fileno())
shutil.copyfile(п, r'C:\seostat\drop\drop-storage\cc-inn-info.json')
print('===ИТОГ===')
print(json.dumps({'инн': len(инн), 'найдено_в_базе': len(out)}, ensure_ascii=False))
