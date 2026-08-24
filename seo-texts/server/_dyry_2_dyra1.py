# -*- coding: utf-8 -*-
"""ДЫРА 1: компании со страницами в кэше, но без паспорта в site_facts.

Прогоняем каждую через ТУ ЖЕ логику, что и _iz_kesha из site_facts.py:
  1) файл кэша <ИНН>.json.gz есть;
  2) ИНН есть в companies и verified <> 'mismatch'   -> иначе выпадает;
  3) site = coalesce(site, cand_site) НЕ пуст        -> иначе выпадает;
  4) ИНН не в propustit (готовые)                    -> у нас паспорта нет вовсе;
Только чтение.
"""
import gzip
import json
import os
import sqlite3
import time

BD = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'
VYHOD = r'C:\sender\_tmp\dyra1.json'

t0 = time.time()
c = sqlite3.connect(BD, uri=True, timeout=30)

# --- ровно тот же запрос, что в _iz_kesha ---
imena = {}
for inn, name, site, cand in c.execute(
        "select inn, coalesce(name,'') , coalesce(site,'') , coalesce(cand_site,'') "
        "from companies where coalesce(verified,'') <> 'mismatch'"):
    imena[str(inn)] = (name, site or cand)
# все компании вообще (включая mismatch) — чтобы отличить «нет в базе» от «mismatch»
vse_komp = {}
for inn, name, site, cand, ver in c.execute(
        "select inn, coalesce(name,''), coalesce(site,''), coalesce(cand_site,''), "
        "coalesce(verified,'') from companies"):
    vse_komp[str(inn)] = (name, site, cand, ver)

sf = {}
for inn, fj, note, pop, fmt, otl, per, ts in c.execute(
        "select inn, coalesce(facts_json,''), coalesce(note,''), coalesce(popytok,0), "
        "coalesce(format,0), coalesce(otlozheno_do,0), coalesce(pererazborov,0), "
        "coalesce(ts,'') from site_facts"):
    sf[str(inn)] = (fj, note, pop, fmt, otl, per, ts)

st_inns = {str(r[0]) for r in c.execute('select distinct inn from stage_log')}
c.close()
print('база прочитана', round(time.time() - t0, 1), 'сек; companies=%d site_facts=%d'
      % (len(vse_komp), len(sf)))

# --- кэш ---
fajly = [n for n in os.listdir(KESH) if n.endswith('.json.gz')]
kesh_inn = {n.split('.')[0]: n for n in fajly}
bez_pasporta = [i for i in kesh_inn if i not in sf]
print('файлов кэша %d; без паспорта %d' % (len(fajly), len(bez_pasporta)))

MARK = b'"html_full_len"'
stranic = {}
t1 = time.time()
oshibok = 0
for k, i in enumerate(bez_pasporta):
    p = os.path.join(KESH, kesh_inn[i])
    try:
        with gzip.open(p, 'rb') as f:
            b = f.read()
        stranic[i] = b.count(MARK)
    except Exception:  # noqa: BLE001
        oshibok += 1
        stranic[i] = -1
    if k % 5000 == 0:
        print(' ...%d/%d %ds' % (k, len(bez_pasporta), time.time() - t1), flush=True)
print('распаковка', round(time.time() - t1), 'сек, сбоев', oshibok)

celi = sorted([i for i in bez_pasporta if stranic.get(i, 0) >= 9],
              key=lambda x: -stranic[x])
print('без паспорта и >=9 страниц:', len(celi))

# --- прогон по логике _iz_kesha ---
prichiny = {}
podrobno = []
for i in celi:
    if i not in vse_komp:
        pr = 'нет в companies'
    else:
        name, site, cand, ver = vse_komp[i]
        if ver == 'mismatch':
            pr = 'verified=mismatch'
        elif not (site or cand):
            pr = 'нет site и cand_site'
        else:
            pr = 'ПРОХОДИТ ФИЛЬТР (должна была разобраться)'
    prichiny[pr] = prichiny.get(pr, 0) + 1
    nm, s, cd, v = vse_komp.get(i, ('', '', '', ''))
    podrobno.append({'inn': i, 'stranic': stranic[i], 'prichina': pr,
                     'name': nm[:70], 'site': s, 'cand_site': cd, 'verified': v,
                     'v_stage_log': i in st_inns})

print('ПРИЧИНЫ:', json.dumps(prichiny, ensure_ascii=False))

# сколько из них вообще есть в stage_log
bez_st = sum(1 for d in podrobno if not d['v_stage_log'])
print('из них нет ни одной записи в stage_log:', bez_st)

# размер текста у целей (медиана) — считаем по-настоящему, json.loads
import statistics  # noqa: E402
znakov = []
for d in podrobno:
    try:
        with gzip.open(os.path.join(KESH, kesh_inn[d['inn']]), 'rb') as f:
            j = json.loads(f.read().decode('utf-8', 'replace'))
        n = len(j.get('text') or '')
        d['znakov_text'] = n
        d['site_v_keshe'] = (j.get('site') or '')[:80]
        d['ts_kesha'] = j.get('ts', '')
        znakov.append(n)
    except Exception:  # noqa: BLE001
        d['znakov_text'] = -1
print('медиана знаков text:', int(statistics.median(znakov)) if znakov else 0)

# --- контроль: а сколько ВСЕГО кандидатов _iz_kesha сейчас видит? ---
# (без учёта готовых: у целей паспорта нет вовсе)
vidit = sum(1 for i in bez_pasporta if i in imena and imena[i][1])
print('всего файлов кэша без паспорта, которые _iz_kesha приняла бы:', vidit)
raspred = {}
for i in bez_pasporta:
    if i not in vse_komp:
        k = 'нет в companies'
    elif vse_komp[i][3] == 'mismatch':
        k = 'verified=mismatch'
    elif not (vse_komp[i][1] or vse_komp[i][2]):
        k = 'нет site и cand_site'
    else:
        k = 'ПРОХОДИТ'
    raspred[k] = raspred.get(k, 0) + 1
print('ВСЕ 28k без паспорта по причинам:', json.dumps(raspred, ensure_ascii=False))

os.makedirs(r'C:\sender\_tmp', exist_ok=True)
with open(VYHOD, 'w', encoding='utf-8') as f:
    json.dump({'celi': podrobno, 'prichiny': prichiny,
               'raspred_vseh_bez_pasporta': raspred,
               'stranic_bez_pasporta': {k: v for k, v in stranic.items() if v >= 3}},
              f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('ИТОГ файл', VYHOD, 'целей', len(celi))
print('30 ПРИМЕРОВ:', json.dumps(
    [{'inn': d['inn'], 'p': d['stranic'], 'z': d.get('znakov_text'),
      'pr': d['prichina'][:22], 'nm': d['name'][:40], 's': d['site'][:30],
      'c': d['cand_site'][:30]} for d in podrobno[:30]], ensure_ascii=False)[:3000])
