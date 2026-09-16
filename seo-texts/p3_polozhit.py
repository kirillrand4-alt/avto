# -*- coding: utf-8 -*-
"""Положить файл на сервер БЕЗ запуска (для модулей, которые только импортируются).

`zapusk_na_servere.py` кладёт и сразу запускает; библиотеке запуск не нужен.
Использование: python3 p3_polozhit.py p3_proekt_lib.py
"""
import base64
import os
import sys

sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
lok = sys.argv[1]
dest = r'C:\sender\_ops\3s_' + os.path.basename(lok)
kod = open(lok, encoding='utf-8').read()
r = R.submit('enrich_contacts', {'op': 'panel_file_put',
                                 'files': [{'dest': dest,
                                            'b64': base64.b64encode(
                                                kod.encode()).decode()}]},
             timeout=300)
print('положено: %s (ответ: %s)' % (dest, str(r.get('data'))[:200]))
