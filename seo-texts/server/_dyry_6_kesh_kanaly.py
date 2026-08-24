# -*- coding: utf-8 -*-
"""Сколько файлов в каждом кэш-каталоге и пересекаются ли они с site_facts."""
import json
import os
import sqlite3

RO = 'file:C:/sender/enrich.db?mode=ro'
c = sqlite3.connect(RO, uri=True, timeout=30)
sf = {str(r[0]) for r in c.execute('select inn from site_facts')}
st = {str(r[0]) for r in c.execute('select distinct inn from stage_log')}
komp = {str(r[0]): (r[1] or '', r[2] or '', r[3] or '') for r in c.execute(
    "select inn, coalesce(site,''), coalesce(cand_site,''), coalesce(verified,'') "
    'from companies')}
c.close()

KAT = [r'C:\seostat\drop\pagecache', r'C:\seostat\drop\pagecache_A_facts',
       r'C:\seostat\drop\pagecache_C_kontakt', r'C:\seostat\drop\pagecache_otkloneno',
       r'C:\seostat\drop\pagecache_staryy_20260813_2036', r'C:\seostat\drop\pagecache_test',
       r'C:\seostat\drop\zenno\gotovo', r'C:\seostat\drop\zenno\razobrano',
       r'C:\seostat\drop\zenno\snimki']
svod = {}
for k in KAT:
    try:
        n = os.listdir(k)
    except Exception as e:  # noqa: BLE001
        svod[k] = {'нет': str(e)[:50]}
        continue
    gz = [x for x in n if x.endswith('.json.gz')]
    inns = {x.split('.')[0] for x in gz}
    ras = {}
    for x in n:
        e = x.split('.', 1)[1] if '.' in x else ''
        ras[e] = ras.get(e, 0) + 1
    svod[k] = {'всего': len(n), 'json_gz': len(gz),
               'расширения': dict(sorted(ras.items(), key=lambda i: -i[1])[:6]),
               'без_паспорта': len(inns - sf),
               'без_stage_log': len(inns - st),
               'нет_в_companies': len([i for i in inns if i not in komp])}
print(json.dumps(svod, ensure_ascii=False, indent=1)[:4500])
