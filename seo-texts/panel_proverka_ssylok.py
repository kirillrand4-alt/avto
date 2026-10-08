# -*- coding: utf-8 -*-
"""Нет ли в копии ссылок, уводящих на боевую панель.

Это главный риск переноса на другой префикс: одна забытая ссылка на /obzvon/... — и
продавец Мейера, кликнув, оказывается в центробежной базе чужой смены, причём обе
страницы выглядят одинаково и подмену он не заметит. Поэтому проверяются не исходники,
а ГОТОВЫЕ страницы: что реально ушло в браузер.
"""
import collections
import io
import os
import re
import subprocess
import sys

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:],
                       capture_output=True, timeout=1500,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8',
                                OBZVON_ROOT_PATH='/obzvon-meyer'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    sys.stderr.write(r.stderr.decode('utf-8', 'replace'))
    raise SystemExit(r.returncode)

os.chdir(KOREN)
sys.path.insert(0, KOREN)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(KOREN, '.env'), override=True)
except Exception:  # noqa: BLE001
    pass
os.environ['OBZVON_ROOT_PATH'] = '/obzvon-meyer'

from app.api import routes_centro_sales as rcs  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

itog = []


def skazat(s):
    itog.append(str(s))
    print(s)


skazat('префикс копии: %r' % get_settings().obzvon_path)
skazat('BP в routes_centro_sales: %r' % rcs.BP)

vnesh = create_app()
vnutr = next(z for z in vars(vnesh).values()
             if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
vnutr.dependency_overrides[rcs.current_user] = lambda: {
    'username': 'admin', 'role': 'admin', 'is_active': 1}

STRANICY = ['/obzvon-meyer/centro', '/obzvon-meyer/centro/stats',
            '/obzvon-meyer/centro/stats?user=user2', '/obzvon-meyer/centro/admin',
            '/obzvon-meyer/centro/spisok', '/obzvon-meyer/centro/park']
chuzhie = collections.Counter()
vsego_ssylok = 0
with TestClient(vnutr) as k:
    for put in STRANICY:
        try:
            o = k.get(put)
        except Exception as e:  # noqa: BLE001
            skazat('%-42s ПАДАЕТ: %s' % (put, str(e)[:90]))
            continue
        if o.status_code != 200:
            skazat('%-42s -> %s  %s' % (put, o.status_code,
                                        o.text[:120].replace('\n', ' ')))
            continue
        t = o.text
        # все ссылки и адреса запросов, какие ушли в браузер
        adresa = re.findall(r'(?:href|src|action|fetch\(|url:)\s*=?\s*["\']([^"\']+)',
                            t) + re.findall(r'["\'](/[a-zA-Z0-9][^"\']*)["\']', t)
        vsego_ssylok += len(adresa)
        plohie = [a for a in adresa
                  if a.startswith('/obzvon/') or a == '/obzvon'
                  or a.startswith('/obzvon/centro')]
        svoi = len([a for a in adresa if a.startswith('/obzvon-meyer')])
        for a in plohie:
            chuzhie[a] += 1
        skazat('%-42s -> 200, %6d знаков, адресов %4d, своих %4d, ЧУЖИХ %d'
               % (put, len(t), len(adresa), svoi, len(plohie)))

skazat('')
if chuzhie:
    skazat('НАЙДЕНЫ ССЫЛКИ НА БОЕВУЮ ПАНЕЛЬ — их надо убирать:')
    for a, n in chuzhie.most_common(20):
        skazat('   %4d x  %s' % (n, a))
else:
    skazat('ссылок на /obzvon/... в готовых страницах НЕТ — утечки на боевую панель нет')
skazat('адресов проверено всего: %d' % vsego_ssylok)

print('\n===== ИТОГ =====')
for s in itog:
    print(s)
