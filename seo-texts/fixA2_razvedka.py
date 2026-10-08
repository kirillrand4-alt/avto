# -*- coding: utf-8 -*-
"""Исправитель A2: разведка (только чтение). Под venv:
  * словари контактов всех компаний – как их отдаёт каталог карточке (centro_catalog.contacts);
  * колонки компании, нужные виду: lpr_roli, lpr_kratko, sayt/website;
  * фильтр «Роль ЛПР»: пункты выпадающего списка и сколько находит каждый (TestClient, админ,
    на копии базы продаж).
-> на дроп fixA2_razvedka.json (с номерами – только дроп/scratchpad, не репо).

    python3 zapusk_na_servere.py fixA2_razvedka.py
"""
import html
import io
import json
import os
import re
import subprocess
import sys

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'

if '--venv' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--venv'], capture_output=True, timeout=1600,
                       cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5000:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
    raise SystemExit(0)

sys.path.insert(0, KOREN)
import zapusk  # noqa: F401,E402
import logging  # noqa: E402
import sqlite3  # noqa: E402
import warnings  # noqa: E402
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
TEST_DB = os.path.join(KOREN, '_bekap', 'fixA2-razv-%d.db' % os.getpid())
src = sqlite3.connect(os.environ['CENTRO_SALES_DB'])
dst = sqlite3.connect(TEST_DB)
src.backup(dst)
src.close()
dst.close()
os.environ['CENTRO_SALES_DB'] = TEST_DB
os.environ['PARK_OCHERED_SALES_DB'] = TEST_DB
from app.services import centro_catalog as cc  # noqa: E402

KL = ('id', 'kind', 'value', 'href', 'person', 'position', 'role', 'vid_nomera', 'vid_pochemu', 'rol_vid', 'lpr',
      'uroven', 'lpr_metka', 'obshchiy_nomer', 'chuzhoy_istochnik', 'sprosit', 'phone_type', 'nomer_ne_lichnyy',
      'has_role', 'source', 'source_url', 'is_tech', 'is_purchaser')
out = {'kontakty': {}, 'kompanii': {}}
kat = sqlite3.connect('file:%s?mode=ro' % str(cc.db_path()), uri=True)
kat.row_factory = sqlite3.Row
kol = [r[1] for r in kat.execute('PRAGMA table_info(company)')]
out['company_kolonki'] = kol
for r in kat.execute('select * from company'):
    d = dict(r)
    out['kompanii'][d['inn']] = {k: d.get(k) for k in ('lpr_roli', 'lpr_kratko', 'sayt', 'website', 'predpriyatie',
                                                      'has_role_phone', 'has_tech', 'lpr_mobilnyy', 'lpr_s_fio')}
    out['kontakty'][d['inn']] = [{k: x.get(k) for k in KL} for x in cc.contacts(d['inn'])]
print('компаний: %d, контактов: %d' % (len(out['kompanii']), sum(len(v) for v in out['kontakty'].values())))
ckol = [r[1] for r in kat.execute('PRAGMA table_info(contact)')]
out['contact_kolonki'] = ckol
print('колонки contact: ' + ', '.join(ckol))

from app.api import routes_centro_sales as rcs  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
filtr = {}
for kto, u in (('admin', {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}),
               ('sales', {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1})):
    vnutr.dependency_overrides[rcs.current_user] = (lambda u=u: u)
    with TestClient(vnutr) as kl:
        t = kl.get(PUT + '/centro').text
        m = re.search(r'<select name="rol_lpr">(.*?)</select>', t, re.S)
        opts = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', m.group(1)) if m else []
        vkl = re.findall(r'call_status=([a-z_]+)', t)
        rez = []
        for v, txt in opts:
            if not v:
                continue
            v = html.unescape(v)
            mm = re.search(r'–\s*(\d+)\s*$', html.unescape(txt))
            n_pok = int(mm.group(1)) if mm else None
            naid = {}
            for cs in ('', 'v_rabote', 'ne_ponravilas', 'dubl'):
                p = {'rol_lpr': v}
                if cs:
                    p['call_status'] = cs
                tt = kl.get(PUT + '/centro', params=p).text
                mt = re.search(r'<b class="total-count">(\d+)', tt)
                naid[cs or 'vsya'] = int(mt.group(1)) if mt else None
            rez.append({'value': v, 'pokazano': n_pok, 'naydeno': naid})
            print('%s %-40s показано %s, найдено %s' % (kto, v, n_pok, naid))
        filtr[kto] = rez
out['filtr_rol_lpr'] = filtr
io.open(os.path.join(DROP, 'fixA2_razvedka.json'), 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, default=str))
try:
    os.remove(TEST_DB)
except OSError:
    pass
print('-> fixA2_razvedka.json')
