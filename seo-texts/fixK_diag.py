# -*- coding: utf-8 -*-
"""fixK (сервер, только чтение, копии баз): какая строка CSV meyer4 не находится в списке очереди (разбор проверки fixK_ball)."""
import csv, io, os, re, sqlite3, subprocess, sys, time
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
if '--vnutri' not in sys.argv:
    papka = os.path.join(KOREN, '_bekap', 'fixK-diag-' + time.strftime('%H%M%S'))
    os.makedirs(papka, exist_ok=True)
    out = []
    for imya in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
        a = sqlite3.connect('file:%s?mode=ro' % os.path.join(KOREN, 'data', imya), uri=True)
        b = sqlite3.connect(os.path.join(papka, imya)); a.backup(b); b.close(); a.close()
        out.append(os.path.join(papka, imya))
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + out, capture_output=True, timeout=900, cwd=KOREN,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    print(r.stdout.decode('utf-8', 'replace')[-5000:], r.stderr.decode('utf-8', 'replace')[-2000:])
    for f in out:
        os.remove(f)
    raise SystemExit(0)
i = sys.argv.index('--vnutri'); TK, TS = sys.argv[i + 1], sys.argv[i + 2]
sys.path.insert(0, KOREN)
import zapusk  # noqa
import logging; logging.disable(logging.CRITICAL)
for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'): os.environ[kk] = TS
for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'): os.environ[kk] = TK
from app.api import routes_centro_sales as rcs
from app.obzvon import create_app
from fastapi.testclient import TestClient
vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
kto = {'u': {'id': 4, 'username': 'meyer4', 'role': 'sales', 'is_active': 1}}
vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
rx_row = re.compile(r'<tr data-href="[^"]*centro\?inn=(\d+)[^"]*">.*?class="chislo tiho och-ball"[^>]*>([-\d.]+)</td>', re.S)
rx_any = re.compile(r'<tr data-href="[^"]*centro\?inn=(\d+)')
with TestClient(vnutr) as kl:
    spis, vse = [], []
    for st in (1, 2, 3):
        t = kl.get('/obzvon-meyer/centro', params={'size': 100, 'page': st}).text
        spis += [x for x, _ in rx_row.findall(t)]
        vse += rx_any.findall(t)
    kto['u'] = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    o = kl.get('/obzvon-meyer/centro/vygruzka.csv', params={'assigned_user': 'meyer4'})
    rows = list(csv.reader(io.StringIO(o.content.decode('utf-8-sig')), delimiter=';'))
    csv_inn = [r[2] for r in rows[1:] if len(r) > 5]
print('список: строк с баллом %d, всего строк %d; CSV %d' % (len(spis), len(vse), len(csv_inn)))
lishnie = [x for x in csv_inn if x not in spis]
print('в CSV, но без балла в списке:', lishnie, 'в списке всего:', [x for x in lishnie if x in vse])
k = sqlite3.connect(TK)
for x in lishnie:
    print(k.execute('select inn, predpriyatie, pometka_ocheredi, bazy from company where inn=?', (x,)).fetchall())
s = sqlite3.connect(TS)
for x in lishnie:
    print(s.execute('select inn, assignment_score, stupen_ocheredi, source_version from company_assignment where inn=?', (x,)).fetchall())
t = kl.get if False else None
