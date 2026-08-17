# -*- coding: utf-8 -*-
"""Залить свой скрипт на сервер и запустить его питоном панели.

Два задания: panel_file_put (иначе panel_py не найдёт файл — он требует
АБСОЛЮТНЫЙ путь и ничего не принимает телом) и panel_py со script/argv.
Аргументы после имени файла уезжают в argv как есть; --timeout=N свой.
"""
import base64
import os
import sys

sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

src = sys.argv[1]
timeout = 4200
argv = []
for a in sys.argv[2:]:
    if a.startswith('--timeout='):
        timeout = int(a.split('=', 1)[1])
    else:
        argv.append(a)

dest = r'C:\sender\_ops' + '\\' + os.path.basename(src)
b = open(src, 'rb').read()
R.submit('enrich_contacts',
         {'op': 'panel_file_put',
          'files': [{'b64': base64.b64encode(b).decode(), 'dest': dest}]},
         wait=True, poll=8, timeout=300)

res = R.submit('enrich_contacts',
               {'op': 'panel_py', 'script': dest, 'argv': argv,
                'timeout': timeout},
               wait=True, poll=12, timeout=timeout + 200)
d = (res or {}).get('data') or {}
print(d.get('stdout_tail') or '')
if d.get('stderr_tail'):
    print('STDERR:', d['stderr_tail'][-2000:], file=sys.stderr)
if d.get('rc') is None:
    import json as _j
    print('СЫРОЙ ОТВЕТ СЕРВЕРА:', _j.dumps(res, ensure_ascii=False)[:1500])
print('rc =', d.get('rc'))
sys.exit(0 if d.get('rc') in (0, None) else 1)
