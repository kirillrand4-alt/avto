# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R
скрипт = sys.argv[1] if len(sys.argv) > 1 else 'svod_lichnyh_nomerov.py'
res = R.submit('enrich_contacts',
               {'op': 'panel_py', 'script': r'C:\sender\server\ops\\' + скрипт,
                'argv': sys.argv[2:], 'timeout': 900}, wait=True, poll=10, timeout=1000)
d = res.get('data') or {}
if d.get('error'):
    print('ОШИБКА РАННЕРА:', d['error'])
else:
    print(d.get('stdout_tail') or ('ПУСТО: ' + str(d)[:400]))
    if d.get('rc'):
        print('rc=%s' % d['rc'], str(d.get('stderr_tail'))[:900])
