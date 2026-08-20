# -*- coding: utf-8 -*-
"""Положить мою копию файла в C:\\sender\\_ops под именем MOYO-<имя>.

Нужна перед выкаткой: каталог C:\\sender\\sender общий с соседней сессией,
и перезаписывать её правку вслепую нельзя. Порядок — положить копию,
сравнить (ops/sverit_s_moim.py), и только потом трогать боевой файл.
"""
import base64
import os
import sys

sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

for src in sys.argv[1:]:
    dest = r'C:\sender\_ops' + '\\MOYO-' + os.path.basename(src)
    b = open(src, 'rb').read()
    R.submit('enrich_contacts',
             {'op': 'panel_file_put',
              'files': [{'b64': base64.b64encode(b).decode(), 'dest': dest}]},
             wait=True, poll=8, timeout=300)
    print(f"{src} -> {dest} ({len(b)} байт)")
