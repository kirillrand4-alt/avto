# -*- coding: utf-8 -*-
"""Положить ops-скрипты на сервер инлайном (b64), без HTTP к дропу.

Инлайн, а не через дроп: внешний GET у сервера рвётся на 384КБ через
hairpin-NAT, а маленькие скрипты и так дешевле приложить к самому заданию.

    python dep.py ops/svod_lichnyh_nomerov.py [ещё файлы...]
"""
import base64
import os
import sys

sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

БАЗА = '/home/user/avto/seo-texts/server'
files = []
for отн in sys.argv[1:]:
    п = os.path.join(БАЗА, отн)
    blob = open(п, 'rb').read()
    files.append({'dest': r'C:\sender\server\\' + отн.replace('/', '\\'),
                  'b64': base64.b64encode(blob).decode()})
    print(f'{отн}: {len(blob)}b')
res = R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': files},
               wait=True, poll=6, timeout=300)
print(res.get('data'))
