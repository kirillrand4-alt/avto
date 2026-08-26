# -*- coding: utf-8 -*-
"""Положить файл по ПРОИЗВОЛЬНОМУ пути на сервере (без запуска).

    python polozhit_fayl.py <локальный> <путь на сервере>
"""
import base64
import sys

sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

src, dest = sys.argv[1], sys.argv[2]
b = open(src, 'rb').read()
R.submit('enrich_contacts',
         {'op': 'panel_file_put',
          'files': [{'b64': base64.b64encode(b).decode(), 'dest': dest}]},
         wait=True, poll=8, timeout=300)
print(f"{src} -> {dest} ({len(b)} байт)")
