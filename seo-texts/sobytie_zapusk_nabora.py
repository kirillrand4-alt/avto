# -*- coding: utf-8 -*-
"""Положить на сервер НЕСКОЛЬКО своих модулей и запустить один из них.

`zapusk_na_servere.py` кладёт ровно один файл, а классификатор стадии состоит из трёх:
sobytie_data.py (даты), sobytie_stadiya.py (стадия), sobytie_v_bazu.py (запись в enrich.db).
Раннер это умеет: у операции panel_file_put ключ `files` - список.

Использование:
    python3 sobytie_zapusk_nabora.py sobytie_v_bazu.py --sozdat --pokazat 5
Первый аргумент - какой из набора запускать, остальные уходят в argv скрипта.
"""
import base64
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(DIR, 'server'))
import run_on_server as R  # noqa: E402

NABOR = ['sobytie_data.py', 'sobytie_stadiya.py', 'sobytie_v_bazu.py']

if len(sys.argv) < 2:
    sys.exit(__doc__)
glavnyy = os.path.basename(sys.argv[1])
argv = sys.argv[2:]

files = []
for imya in NABOR:
    put = os.path.join(DIR, imya)
    kod = open(put, encoding='utf-8').read()
    files.append({'dest': r'C:\sender\_ops\3s_' + imya,
                  'b64': base64.b64encode(kod.encode()).decode()})
R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': files}, timeout=300)
print('положено файлов: %d' % len(files), file=sys.stderr)

dest = r'C:\sender\_ops\3s_' + glavnyy
r = R.submit('enrich_contacts',
             {'op': 'panel_py', 'script': dest, 'argv': argv, 'timeout': 1700},
             timeout=1800)
d = r.get('data') or {}
print('rc=%s' % d.get('rc'), file=sys.stderr)
print((d.get('stdout_tail') or '')[-6000:])
err = (d.get('stderr_tail') or '')
if err:
    print('--- stderr ---\n' + err[-2500:], file=sys.stderr)
