# -*- coding: utf-8 -*-
"""ДЫРА 1, часть 2: живой ли цикл, что реально возвращает _iz_kesha.

Зовём НАСТОЯЩУЮ site_facts._iz_kesha с теми же аргументами, что и sobrat(),
но подсунув соединение только на чтение. Ничего не пишем.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, r'C:\sender\server')
RO = 'file:C:/sender/enrich.db?mode=ro'

# --- 1. жив ли цикл разбора и когда последний паспорт ---
c = sqlite3.connect(RO, uri=True, timeout=30)
print('site_facts всего:', c.execute('select count(*) from site_facts').fetchone()[0])
print('последние ts:', json.dumps([list(r) for r in c.execute(
    "select substr(ts,1,13) h, count(*) from site_facts where ts<>'' "
    'group by h order by h desc limit 14')], ensure_ascii=False))
print('карточек с содержимым:', c.execute(
    "select count(*) from site_facts where coalesce(facts_json,'')<>''").fetchone()[0])

FORMAT = 2
gotovye = {str(r[0]) for r in c.execute(
    "select inn from site_facts where coalesce(popytok,0) >= 3 "
    "or coalesce(otlozheno_do,0) > ? "
    "or (coalesce(facts_json,'')<>'' and coalesce(format,0) >= ?)",
    (time.time(), FORMAT))}
print('gotovye (propustit):', len(gotovye))
c.close()

# --- 2. процессы python на сервере ---
try:
    out = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get',
                          'ProcessId,CommandLine'], capture_output=True, text=True,
                         timeout=60).stdout
    stroki = [s.strip()[:150] for s in out.splitlines() if s.strip()]
    print('ПРОЦЕССЫ python (%d):' % len(stroki))
    for s in stroki[:20]:
        print('  ', s)
except Exception as e:  # noqa: BLE001
    print('процессы не прочитались:', str(e)[:120])

# --- 3. настоящий _iz_kesha ---
import site_facts as SF  # noqa: E402

_orig = SF.sqlite3.connect


def _ro(*a, **k):
    return _orig(RO, uri=True, timeout=30)


SF.sqlite3.connect = _ro
c2 = _orig(RO, uri=True, timeout=30)
svezhest = {str(r[0]): SF._vremya_pasporta(r[1]) for r in c2.execute(
    "select inn, coalesce(ts,'') from site_facts where coalesce(facts_json,'')<>''")}
c2.close()
t0 = time.time()
kand = SF._iz_kesha(200, gotovye, svezhest)
SF.sqlite3.connect = _orig
print('_iz_kesha(200) вернула:', len(kand), 'за', round(time.time() - t0, 1), 'сек')
print('из них помечено на переразбор:', sum(1 for k in kand if k.get('pererazbor')))
print('первые 8:', json.dumps(kand[:8], ensure_ascii=False)[:900])

# --- 4. кто в кэше без паспорта и БЕЗ stage_log ---
d1 = json.load(open(r'C:\sender\_tmp\dyra1.json', encoding='utf-8'))
stranic = d1['stranic_bez_pasporta']
c = sqlite3.connect(RO, uri=True, timeout=30)
st_inns = {str(r[0]) for r in c.execute('select distinct inn from stage_log')}
komp = {}
for r in c.execute("select inn, coalesce(name,''), coalesce(site,''), "
                   "coalesce(cand_site,''), coalesce(verified,''), "
                   "coalesce(istochnik_kompanii,''), coalesce(site_source,'') "
                   'from companies'):
    komp[str(r[0])] = tuple(r[1:])
sf_inn = {str(r[0]) for r in c.execute('select inn from site_facts')}
c.close()

KESH = r'C:\seostat\drop\pagecache'
kesh_inn = [n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')]
bez_p = [i for i in kesh_inn if i not in sf_inn]
bez_st = [i for i in bez_p if i not in st_inns]
print('кэш без паспорта:', len(bez_p), '; из них БЕЗ stage_log:', len(bez_st))
raspr = {}
for i in bez_st:
    if i not in komp:
        k = 'нет в companies'
    elif komp[i][3] == 'mismatch':
        k = 'verified=mismatch'
    elif not (komp[i][1] or komp[i][2]):
        k = 'нет site и cand_site'
    else:
        k = 'ПРОХОДИТ'
    raspr[k] = raspr.get(k, 0) + 1
print('без stage_log по причинам:', json.dumps(raspr, ensure_ascii=False))
p9 = [i for i in bez_st if stranic.get(i, 0) >= 9]
print('без stage_log и >=9 страниц:', len(p9))
r9 = {}
for i in p9:
    if i not in komp:
        k = 'нет в companies'
    elif komp[i][3] == 'mismatch':
        k = 'verified=mismatch'
    elif not (komp[i][1] or komp[i][2]):
        k = 'нет site и cand_site'
    else:
        k = 'ПРОХОДИТ'
    r9[k] = r9.get(k, 0) + 1
print('они же по причинам:', json.dumps(r9, ensure_ascii=False))

with open(r'C:\sender\_tmp\dyra1b.json', 'w', encoding='utf-8') as f:
    json.dump({'kandidaty_iz_kesha': kand[:200], 'bez_stage_log': bez_st,
               'bez_stage_log_9str': p9, 'raspr': raspr, 'raspr9': r9,
               'gotovyh': len(gotovye)}, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('ИТОГ: файл dyra1b.json записан')
