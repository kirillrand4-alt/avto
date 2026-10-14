# -*- coding: utf-8 -*-
r"""fixT: запустить на сервере скрипт конвейера fixQ (или любой другой) ПОД ИМЕНЕМ С ПРЕФИКСОМ fixT – чтобы не затереть
серверные копии других агентов (`zapusk_na_servere.py` кладёт файл как `3s_<имя>`; здесь – `3s_fixT_<имя>`).
Код не копируется в репо: на сервер уходит сам файл fixQ_*.py, параметры fixT – аргументами.

    python3 fixT_zapusk.py fixQ_vzyat.py fixT-1410-                    # снимок баз и кода -> дроп fixT-1410-bazy.zip
    python3 fixT_zapusk.py fixQ_dadata.py fixT-proverka-rf.txt fixT-dadata.json
    python3 fixT_zapusk.py fixQ_zamena.py --prefiks fixT --plan fixT-plan.json --suhoy
    [--dop fixS_metki.py,fixS_ball.py]  – положить рядом и эти файлы (как 3s_<имя>, без префикса: так их ищет fixQ_zamena)
"""
import base64
import os
import sys

sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

ZDES = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) < 2:
    sys.exit(__doc__)
argv = sys.argv[2:]
dop = []
if '--dop' in argv:
    i = argv.index('--dop')
    dop = [x for x in argv[i + 1].split(',') if x]
    del argv[i:i + 2]
lok = os.path.join(ZDES, os.path.basename(sys.argv[1]))
imya = os.path.basename(lok)
dest = r'C:\sender\_ops\3s_' + (imya if imya.startswith('fixT_') else 'fixT_' + imya)
fayly = [{'dest': dest, 'b64': base64.b64encode(open(lok, 'rb').read()).decode()}]
for f in dop:
    fayly.append({'dest': r'C:\sender\_ops\3s_' + os.path.basename(f),
                  'b64': base64.b64encode(open(os.path.join(ZDES, os.path.basename(f)), 'rb').read()).decode()})
R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fayly}, timeout=300)
print('положено: %s' % ', '.join(f['dest'] for f in fayly), file=sys.stderr)
r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'argv': argv, 'timeout': 1700}, timeout=1800)
d = r.get('data') or {}
print('rc=%s' % d.get('rc'), file=sys.stderr)
print((d.get('stdout_tail') or '')[-6000:])
err = d.get('stderr_tail') or ''
if err:
    print('--- stderr ---\n' + err[-3000:], file=sys.stderr)
