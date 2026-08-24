# -*- coding: utf-8 -*-
"""Разведка: схема таблиц enrich.db, размеры, версии серверных файлов.

Только чтение. Ничего не пишет в базы.
"""
import hashlib
import json
import os
import sqlite3
import time

BD = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'

out = {}
c = sqlite3.connect(BD, uri=True, timeout=30)
c.row_factory = sqlite3.Row

tabl = [r[0] for r in c.execute(
    "select name from sqlite_master where type='table' order by name")]
out['tablicy'] = tabl

shema = {}
for t in tabl:
    try:
        cols = [(r[1], r[2]) for r in c.execute('PRAGMA table_info(%s)' % t)]
        n = c.execute('select count(*) from "%s"' % t).fetchone()[0]
        shema[t] = {'kolonki': cols, 'strok': n}
    except Exception as e:  # noqa: BLE001
        shema[t] = {'oshibka': str(e)[:200]}
out['shema'] = shema

# файлы на сервере: размер+хэш, чтобы понять, совпадает ли репозиторий с сервером
fajly = {}
for p in (r'C:\sender\server\site_facts.py', r'C:\sender\server\fakty_cikl.py',
          r'C:\sender\server\enrich_contacts.py', r'C:\sender\server\roli_telefonov.py',
          r'C:\sender\server\zenka_v_ochered.py', r'C:\sender\server\zenka_dozor.py',
          r'C:\sender\gen_provider.py'):
    try:
        b = open(p, 'rb').read()
        fajly[os.path.basename(p)] = {'bajt': len(b),
                                      'sha': hashlib.sha256(b).hexdigest()[:16],
                                      'mtime': time.strftime(
                                          '%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(p)))}
    except Exception as e:  # noqa: BLE001
        fajly[os.path.basename(p)] = {'oshibka': str(e)[:120]}
out['fajly'] = fajly

# кэш
t0 = time.time()
nn = os.listdir(KESH)
gz = [n for n in nn if n.endswith('.json.gz')]
out['kesh'] = {'vsego_fajlov': len(nn), 'json_gz': len(gz),
               'ne_cifrovoe_imya': sum(1 for n in gz if not n.split('.')[0].isdigit()),
               'sek_listdir': round(time.time() - t0, 1)}

# последние записи журнала стадий
try:
    out['stage_top'] = [dict(r) for r in c.execute(
        'select stage, count(*) n from stage_log group by stage order by n desc limit 25')]
except Exception as e:  # noqa: BLE001
    out['stage_top'] = str(e)[:200]

os.makedirs(r'C:\sender\_tmp', exist_ok=True)
p = r'C:\sender\_tmp\dyry-shema.json'
with open(p, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
c.close()
print(json.dumps(out, ensure_ascii=False)[:5500])
