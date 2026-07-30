# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R
res = R.submit('enrich_contacts',
               {'op': 'panel_py', 'script': r'C:\sender\server\ops\plany_import.py',
                'argv': [], 'timeout': 1400}, wait=True, poll=12, timeout=1500)
d = res.get('data') or {}
if d.get('error'):
    print('ОШИБКА РАННЕРА:', d['error'])
else:
    print(d.get('stdout_tail') or ('ПУСТО: ' + str(d)[:300]))
    if d.get('returncode'):
        print('rc=%s' % d['returncode'], str(d.get('stderr_tail'))[:600])
