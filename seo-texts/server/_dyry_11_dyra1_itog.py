# -*- coding: utf-8 -*-
"""ДЫРА 1, окончательный разбор.

Зовём НАСТОЯЩУЮ site_facts._iz_kesha без предела и сверяем: кто из компаний с
кэшем и без паспорта в неё попал, а кто нет и на каком именно условии.
Плюс реконструкция «до долива базы обзвона».
Только чтение (соединение подменено на mode=ro).
"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender\server')
RO = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'

import site_facts as SF  # noqa: E402

_orig = SF.sqlite3.connect
SF.sqlite3.connect = lambda *a, **k: _orig(RO, uri=True, timeout=60)

c = _orig(RO, uri=True, timeout=60)
FORMAT = SF.FORMAT
gotovye = {str(r[0]) for r in c.execute(
    "select inn from site_facts where coalesce(popytok,0) >= 3 "
    "or coalesce(otlozheno_do,0) > ? "
    "or (coalesce(facts_json,'')<>'' and coalesce(format,0) >= ?)",
    (time.time(), FORMAT))}
svezhest = {str(r[0]): SF._vremya_pasporta(r[1]) for r in c.execute(
    "select inn, coalesce(ts,'') from site_facts where coalesce(facts_json,'')<>''")}
sf_inn = {str(r[0]) for r in c.execute('select inn from site_facts')}
komp = {}
for r in c.execute("select inn, coalesce(name,''), coalesce(site,''), coalesce(cand_site,''), "
                   "coalesce(verified,''), coalesce(istochnik_kompanii,''), "
                   "coalesce(site_source,''), coalesce(updated_at,'') from companies"):
    komp[str(r[0])] = tuple(r[1:])
stadii = {}
for inn, st in c.execute('select inn, group_concat(distinct stage) from stage_log group by inn'):
    stadii[str(inn)] = st or ''
ist_raspr = {}
for r in c.execute("select coalesce(istochnik_kompanii,'(пусто)'), count(*) from companies "
                   'group by 1 order by 2 desc limit 15'):
    ist_raspr[r[0]] = r[1]
zhurnal = {str(r[0]) for r in c.execute('select distinct inn from obzvon_merge_b_journal')}
polya = {}
for r in c.execute('select pole, count(*) from obzvon_merge_b_journal group by 1 '
                   'order by 2 desc limit 12'):
    polya[r[0]] = r[1]
c.close()
print('istochnik_kompanii:', json.dumps(ist_raspr, ensure_ascii=False))
print('поля журнала слияния:', json.dumps(polya, ensure_ascii=False))
print('ИНН в журнале слияния:', len(zhurnal))

# --- настоящая выборка ---
t0 = time.time()
kand = SF._iz_kesha(10 ** 6, gotovye, svezhest)
SF.sqlite3.connect = _orig
vydano = {k['inn'] for k in kand}
print('_iz_kesha(без предела) вернула %d компаний за %.1f сек' % (len(kand), time.time() - t0))

d1 = json.load(open(r'C:\sender\_tmp\dyra1.json', encoding='utf-8'))
stranic = d1['stranic_bez_pasporta']
kesh_inn = [n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')]
bez_p = [i for i in kesh_inn if i not in sf_inn]


def verdikt(i):
    """Ровно те условия, что стоят в _iz_kesha, по порядку."""
    if i not in komp:
        return 'нет строки в companies -> `if inn not in imena: continue`'
    if komp[i][3] == 'mismatch':
        return "verified='mismatch' -> отсеян запросом imena"
    if not (komp[i][1] or komp[i][2]):
        return 'site и cand_site пусты -> `if not site: continue`'
    return 'ПРОХОДИТ (стоит в очереди разбора)'


svod = {}
sverka_ok = 0
sverka_bit = []
for i in bez_p:
    v = verdikt(i)
    svod[v] = svod.get(v, 0) + 1
    if (v.startswith('ПРОХОДИТ')) == (i in vydano):
        sverka_ok += 1
    else:
        sverka_bit.append((i, v, i in vydano))
print('КЭШ БЕЗ ПАСПОРТА:', len(bez_p))
print('по условиям _iz_kesha:', json.dumps(svod, ensure_ascii=False))
print('сверка вердикта с реальной выдачей функции: совпало %d, разошлось %d'
      % (sverka_ok, len(sverka_bit)))
if sverka_bit:
    print('  примеры расхождений:', json.dumps(sverka_bit[:5], ensure_ascii=False))

# то же среди тех, у кого >=9 страниц
p9 = [i for i in bez_p if stranic.get(i, 0) >= 9]
svod9 = {}
for i in p9:
    v = verdikt(i)
    svod9[v] = svod9.get(v, 0) + 1
print('из них >=9 страниц:', len(p9), '->', json.dumps(svod9, ensure_ascii=False))

# --- реконструкция «до долива» ---
# компания «приехала обзвоном», если её ИНН есть в журнале слияния и в stage_log
# у неё нет ни одной стадии, кроме обзвон-merge
prishli_obzvonom = [i for i in bez_p if i in zhurnal and stadii.get(i, '') == 'обзвон-merge']
print('кэш без паспорта, приехали обзвоном (журнал + только стадия обзвон-merge):',
      len(prishli_obzvonom))
print('  из них >=9 страниц:', sum(1 for i in prishli_obzvonom if stranic.get(i, 0) >= 9))
zablok = [i for i in bez_p if not verdikt(i).startswith('ПРОХОДИТ')]
print('ЗАБЛОКИРОВАНЫ НАВСЕГДА (не попадут в разбор никогда):', len(zablok))
zab9 = [i for i in zablok if stranic.get(i, 0) >= 9]
print('  из них >=9 страниц:', len(zab9))

# --- 30 конкретных ИНН, проведённых через логику ---
primery = []
for i in sorted(zab9, key=lambda x: -stranic.get(x, 0))[:30]:
    n, s, cs, v, ik, ss, ua = komp.get(i, ('',) * 7)
    primery.append({'inn': i, 'stranic': stranic.get(i, 0), 'name': n[:52],
                    'site': s[:40], 'cand_site': cs[:40], 'verified': v,
                    'istochnik_kompanii': ik[:20], 'site_source': ss[:20],
                    'stadii': stadii.get(i, '(нет)')[:50],
                    'v_vydache_iz_kesha': i in vydano, 'verdikt': verdikt(i)})
print('30 ЗАБЛОКИРОВАННЫХ ИНН, проведённых через логику:')
for p in primery:
    print(' ', p['inn'], '|стр', p['stranic'], '|', p['verdikt'][:46],
          '|выдача:', p['v_vydache_iz_kesha'], '|', p['name'][:26],
          '|site:', p['site'][:22] or '-', '|cand:', p['cand_site'][:22] or '-')

with open(r'C:\sender\_tmp\dyra1_itog.json', 'w', encoding='utf-8') as f:
    json.dump({'bez_pasporta': len(bez_p), 'po_usloviyam': svod, 'po_usloviyam_9str': svod9,
               'zablokirovany': zablok, 'zablokirovany_9str': zab9,
               'primery30': primery, 'sverka_razoshlos': sverka_bit[:50],
               'prishli_obzvonom': len(prishli_obzvonom),
               'vydano_iz_kesha': len(kand)}, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('ИТОГ записан: dyra1_itog.json')
