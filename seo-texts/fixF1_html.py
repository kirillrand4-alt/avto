# -*- coding: utf-8 -*-
"""fixF1: только чтение. Рендер страниц панели TestClient-ом на ВРЕМЕННОЙ копии базы продаж
(живой код C:\\centro2\\app) -> дроп fixF1-html.zip (для скриншотов 1366×768)."""
import io, os, sqlite3, subprocess, sys, zipfile
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
DROP = r'C:\seostat\drop\drop-storage'
if '--run' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--run'], capture_output=True, timeout=900, cwd=KOREN,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    print(r.stdout.decode('utf-8', 'replace')[-3000:], r.stderr.decode('utf-8', 'replace')[-2000:] if r.returncode else '')
    raise SystemExit(0)
sys.path.insert(0, KOREN)
import zapusk  # noqa: F401
import logging, warnings
warnings.filterwarnings('ignore'); logging.disable(logging.CRITICAL)
T = os.path.join(KOREN, '_bekap', 'fixF1-html-%d.db' % os.getpid())
s = sqlite3.connect('file:%s?mode=ro' % os.environ['CENTRO_SALES_DB'], uri=True); d = sqlite3.connect(T); s.backup(d); d.close(); s.close()
os.environ['CENTRO_SALES_DB'] = os.environ['PARK_OCHERED_SALES_DB'] = T
from app.api import routes_centro_sales as rcs
from app.obzvon import create_app
from fastapi.testclient import TestClient
vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
kto = {}
vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
z = zipfile.ZipFile(os.path.join(DROP, 'fixF1-html.zip'), 'w', zipfile.ZIP_DEFLATED)
z.write(os.path.join(KOREN, 'app', 'static', 'css', 'centro.css'), 'centro.css')
with TestClient(vnutr) as kl:
    for imya, u, url in (('meyer2_card_1829013726', 'meyer2', '/centro?inn=1829013726'),
                         ('meyer2_list', 'meyer2', '/centro?size=20'),
                         ('admin_card_3623007585', 'meyer_admin', '/centro?inn=3623007585'),
                         ('admin_card_4401163232', 'meyer_admin', '/centro?inn=4401163232'),
                         ('admin_list_pometka', 'meyer_admin', '/centro?pometka_och=est')):
        kto['u'] = {'id': 0 if u == 'meyer_admin' else 2, 'username': u, 'role': 'admin' if u == 'meyer_admin' else 'sales', 'is_active': 1}
        o = kl.get('/obzvon-meyer' + url)
        print(imya, o.status_code, len(o.text))
        z.writestr(imya + '.html', o.text)
z.close()
import gc; gc.collect()
try: os.remove(T)
except OSError as e: print('копия не удалена', e)
