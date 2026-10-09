# -*- coding: utf-8 -*-
r"""fixG: только чтение. Карточки указанных ИНН глазами админа и их продавца – на ВРЕМЕННЫХ копиях баз
(GET /centro пишет назначения). HTML – на дроп fixG-karta-<ИНН>.html; печать: блок «Холдинг», верх
контактов (ФИО/должность/роль, без номеров), «Важность», балл очереди, строка ЛПР в списке.

    python3 zapusk_na_servere.py fixG_karta.py ИНН[,ИНН...]
"""
import html as H
import io
import os
import re
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
if '--vnutri' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True, timeout=1200,
                       cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5800:] + r.stderr.decode('utf-8', 'replace')[-2000:])
    raise SystemExit(r.returncode)
sys.path.insert(0, KOREN)
import zapusk  # noqa: F401,E402
import logging  # noqa: E402
import warnings  # noqa: E402
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
TMP = os.path.join(KOREN, '_bekap', 'fixG-karta-%s' % time.strftime('%Y%m%d-%H%M%S'))
os.makedirs(TMP, exist_ok=True)
puti = {}
for kl, imya in (('CENTRO_SALES_DB', 'sales.db'), ('CENTRIFUGAL_DB', 'kat.db')):
    a = sqlite3.connect('file:%s?mode=ro' % os.environ[kl], uri=True)
    b = sqlite3.connect(os.path.join(TMP, imya))
    a.backup(b)
    b.close()
    a.close()
    puti[kl] = os.path.join(TMP, imya)
for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
    os.environ[kk] = puti['CENTRO_SALES_DB']
for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
    os.environ[kk] = puti['CENTRIFUGAL_DB']
from app.api import routes_centro_sales as rcs  # noqa: E402
from app.services import centro_catalog as cat  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

s = sqlite3.connect(puti['CENTRO_SALES_DB'])
vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
k = sqlite3.connect(puti['CENTRIFUGAL_DB'])
k.row_factory = sqlite3.Row
vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
kto = {}
vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
with TestClient(vnutr) as kl:
    for inn in sys.argv[sys.argv.index('--vnutri') + 1].split(','):
        c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
        p = vlad.get(inn)
        kto['u'] = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
        t = kl.get(PUT + '/centro', params={'inn': inn}).text
        io.open(os.path.join(DROP, 'fixG-karta-%s.html' % inn), 'w', encoding='utf-8').write(t)
        kto['u'] = {'id': 1, 'username': p, 'role': 'sales', 'is_active': 1}
        o = kl.get(PUT + '/centro', params={'inn': inn})
        sp = kl.get(PUT + '/centro', params={'q': inn}).text
        stroka = re.search(r'<tr data-href="[^"]*inn=%s.*?</tr>' % inn, sp, re.S)
        lpr_v_spiske = re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', stroka.group(0))))[:260] if stroka else '–'
        print('=' * 90)
        print('%s %s · продавец %s · карточка админа 200, продавца %s · Важность %s · балл %s' % (
            inn, c['predpriyatie'], p, o.status_code, c['moy_prioritet'],
            (re.search(r'<b>Балл очереди</b>\s*([\d.]+)', t) or [None, '?'])[1]))
        print('   холдинг в карточке: %s' % ('kholding-section' in t))
        print('   регион %s · пояс UTC+%s · сегмент %s · отрасль %s · попадание %s · чей сайт: %s' % (
            c['region'], c['chas_poyas'], c['segment'], c['otrasl'], c['popadanie'], c['proverka_sayta']))
        print('   lpr_kratko: %s' % re.sub(r'\+7 ?9\d\d ?\d{3}-?(\d\d)-?\d\d', r'+7 9xx xxx-\1-xx', c['lpr_kratko'] or ''))
        print('   строка списка: %s' % re.sub(r'\+7 ?9\d\d ?\d{3}-?(\d\d)-?\d\d', r'+7 9xx xxx-\1-xx', lpr_v_spiske))
        for x in cat.contacts(inn)[:7]:
            print('   %s %-12s %-26s | %-30s | %s' % ('ВЕРХ' if x['has_role'] else 'низ ', x['vid_nomera'][:12], (x['person'] or '')[:26],
                                                  (x['position'] or '')[:30], x['rol_vid']))
for f in os.listdir(TMP):
    try:
        os.remove(os.path.join(TMP, f))
    except OSError:
        pass
