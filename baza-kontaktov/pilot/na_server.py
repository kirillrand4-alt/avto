# -*- coding: utf-8 -*-
"""Положить файлы пилота в C:\\sender\\_ops\\baza_pilot\\ и запустить там скрипт.

    python3 na_server.py <скрипт.py> [аргументы...]     # файлы пилота + стоп-лист/минус-слова
"""
import base64
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(DIR, '..', '..', 'seo-texts', 'server'))
import run_on_server as R  # noqa: E402

DST = 'C:\\sender\\_ops\\baza_pilot\\'
FILES = [sys.argv[1], 'obrabotka.py', 'sbor_serp.py', 'analiz.py', 'balans.py', 'pusk.py', 'pilot_zaprosy.csv', 'idei_zaprosy.csv', 'idei_analiz.py',
         '../stop_domeny.txt', '../minus_slova.txt']
put = []
for f in FILES:
    p = os.path.join(DIR, f)
    if os.path.exists(p) and not any(x['dest'] == DST + os.path.basename(f) for x in put):
        # стоп-лист и минус-слова кладём рядом: analiz ищет их в DIR/..; дублируем в обе папки
        put.append({'dest': DST + os.path.basename(f), 'b64': base64.b64encode(open(p, 'rb').read()).decode()})
        if f.startswith('../'):
            put.append({'dest': 'C:\\sender\\_ops\\' + os.path.basename(f),
                        'b64': base64.b64encode(open(p, 'rb').read()).decode()})
r = R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': put}, timeout=300)
if not (r.get('data') or {}).get('ok'):
    sys.exit('panel_file_put: %s' % str(r)[:500])
r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': DST + sys.argv[1], 'argv': sys.argv[2:],
                                 'timeout': 1700}, timeout=1800)
d = r.get('data') or {}
print('rc=%s' % d.get('rc'), file=sys.stderr)
print((d.get('stdout_tail') or '')[-6000:] or str(r)[:1500])
if d.get('stderr_tail'):
    print('--- stderr ---\n' + d['stderr_tail'][-3000:], file=sys.stderr)
