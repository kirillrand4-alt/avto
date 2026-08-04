# -*- coding: utf-8 -*-
"""Запустить ШТАТНЫЙ оп сервера (он уже лежит там), не заливая ничего.

Заливка нужна только моим скриптам. `leadership.py` и прочие штатные опы живут
в C:\sender\server\ops — их надо просто вызвать с аргументами.

Запуск: python zapusk_opa.py <имя_опа.py> [аргументы...]
"""
import json
import sys

sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

скрипт = r'C:\sender\server\ops' + '\\' + sys.argv[1]
res = R.submit('enrich_contacts',
               {'op': 'panel_py', 'script': скрипт, 'argv': sys.argv[2:],
                'timeout': 1500}, wait=True, poll=15, timeout=1700)
d = res.get('data') or {}
print(d.get('stdout_tail') or '')
if d.get('stderr_tail'):
    print('STDERR:', d['stderr_tail'][-1500:])
print('rc =', d.get('rc'))
