# -*- coding: utf-8 -*-
"""Положить скрипт в C:\\sender\\_ops, НЕ запуская его.

Нужно, когда скрипт запускается не сам, а через обёртку (cherez_bazu.py):
раннер кладёт на сервер только тот файл, который ему назвали.
"""
import base64
import os
import sys

sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

for src in sys.argv[1:]:
    dest = r'C:\sender\_ops' + '\\' + os.path.basename(src)
    b = open(src, 'rb').read()
    R.submit('enrich_contacts',
             {'op': 'panel_file_put',
              'files': [{'b64': base64.b64encode(b).decode(), 'dest': dest}]},
             wait=True, poll=8, timeout=300)
    print(f"{src} -> {dest} ({len(b)} байт)")
