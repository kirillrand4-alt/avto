# -*- coding: utf-8 -*-
"""Цена починки дыры 1: у скольких заблокированных «нет site» сайт ДОКАЗУЕМ.

Доказательство то же, что у конвейера: ИНН (или ОГРН) компании стоит на её же
странице в кэше -> привязка подтверждена, cand_site можно ставить безопасно.
Только чтение.
"""
import gzip
import json
import os
import re
import sqlite3
import time

RO = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'

d1 = json.load(open(r'C:\sender\_tmp\dyra1_itog.json', encoding='utf-8'))
zablok = set(d1['zablokirovany'])
stranic9 = set(d1['zablokirovany_9str'])

c = sqlite3.connect(RO, uri=True, timeout=60)
komp = {}
for r in c.execute("select inn, coalesce(name,''), coalesce(site,''), coalesce(cand_site,''), "
                   "coalesce(verified,''), coalesce(ogrn,'') from companies"):
    komp[str(r[0])] = tuple(r[1:])
# темп разбора за сутки
tempo = [list(r) for r in c.execute(
    "select substr(ts,1,10) d, count(*) from site_facts where ts>='2026-08-20' "
    'group by d order by d')]
c.close()
print('паспортов в день:', json.dumps(tempo, ensure_ascii=False))

bez_sajta = [i for i in zablok if i in komp and komp[i][3] != 'mismatch'
             and not (komp[i][1] or komp[i][2])]
print('заблокированы из-за пустых site/cand_site:', len(bez_sajta))

t0 = time.time()
dokazan, ne_dokazan, bez_fajla = [], [], 0
for k, inn in enumerate(bez_sajta):
    p = os.path.join(KESH, inn + '.json.gz')
    if not os.path.exists(p):
        bez_fajla += 1
        continue
    try:
        with gzip.open(p, 'rb') as f:
            j = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        bez_fajla += 1
        continue
    ogrn = re.sub(r'\D', '', komp[inn][4])
    sajt = (j.get('site') or '')
    nash = False
    for pg in (j.get('pages') or []):
        h = pg.get('html') or ''
        cifry = re.sub(r'\D', '', h)
        if inn in cifry or (ogrn and ogrn in cifry):
            nash = True
            break
    rec = {'inn': inn, 'name': komp[inn][0][:46], 'kesh_site': sajt[:50],
           'stranic': len(j.get('pages') or []), 'devyat': inn in stranic9,
           'istochnik': j.get('istochnik', 'enrich')}
    (dokazan if nash else ne_dokazan).append(rec)
    if k % 800 == 0:
        print('  ...%d/%d %ds' % (k, len(bez_sajta), time.time() - t0), flush=True)

print('ПРОВЕРЕНО за %ds' % (time.time() - t0))
print('ИНН/ОГРН компании НАЙДЕН на её страницах (привязка доказана):', len(dokazan))
print('  из них >=9 страниц:', sum(1 for r in dokazan if r['devyat']))
print('НЕ найден (привязка недоказуема, ставить сайт нельзя):', len(ne_dokazan))
print('  из них >=9 страниц:', sum(1 for r in ne_dokazan if r['devyat']))
print('файл кэша не прочитался:', bez_fajla)
dom = {}
for r in dokazan:
    d = re.sub(r'^https?://(www\.)?', '', r['kesh_site']).split('/')[0]
    dom[d] = dom.get(d, 0) + 1
print('топ доменов среди доказанных:', json.dumps(
    dict(sorted(dom.items(), key=lambda x: -x[1])[:10]), ensure_ascii=False)[:600])

with open(r'C:\sender\_tmp\dyra1_pochinka.json', 'w', encoding='utf-8') as f:
    json.dump({'dokazan': dokazan, 'ne_dokazan': ne_dokazan,
               'bez_fajla': bez_fajla, 'tempo': tempo}, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('30 ПРИМЕРОВ ДОКАЗАННЫХ:')
for r in sorted(dokazan, key=lambda x: -x['stranic'])[:30]:
    print(' ', r['inn'], '|стр', r['stranic'], '|', r['kesh_site'][:40], '|', r['name'][:34])
