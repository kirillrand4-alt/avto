# -*- coding: utf-8 -*-
"""Чем именно различаются шапки разных страниц — построчный дифф, без догадок."""
import difflib
import logging
import os
import re
import subprocess
import sys
import warnings

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
PUT = '/obzvon-meyer'
if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    r = subprocess.run([VENV, os.path.abspath(__file__)], capture_output=True, timeout=900,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8', OBZVON_ROOT_PATH=PUT))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    if r.returncode:
        sys.stdout.write(r.stderr.decode('utf-8', 'replace')[-2000:])
    raise SystemExit(r.returncode)

warnings.filterwarnings('ignore')
for n in ('httpx', 'httpcore', 'app'):
    logging.getLogger(n).setLevel(logging.CRITICAL)
os.chdir(KOREN)
sys.path.insert(0, KOREN)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(KOREN, '.env'), override=True)
os.environ['OBZVON_ROOT_PATH'] = PUT
from app.api import routes_centro_sales as rcs  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from app.web import templates  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

print('глобальные переменные Jinja: base_path=%r, bp=%r'
      % (templates.env.globals.get('base_path', '<нет>'), templates.env.globals.get('bp', '<нет>')))
vnutr = next(z for z in vars(create_app()).values()
             if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
vnutr.dependency_overrides[rcs.current_user] = lambda: {
    'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}


def shapka(t):
    m = re.search(r'<header class="topbar">.*?</header>', t, re.S)
    return re.sub(r'\s*class="active"', '', m.group(0)) if m else ''


with TestClient(vnutr) as k:
    st = {s: k.get(PUT + s) for s in ('/centro', '/centro/stats', '/centro/admin',
                                       '/centro/spisok', '/centro/park', '/centro/park/0255010527')}
etalon = shapka(st['/centro'].text)
for s, o in st.items():
    sh = shapka(o.text)
    print('\n=== %s -> %s, шапка %d знаков, %s' % (s, o.status_code, len(sh),
          'совпадает с /centro' if sh == etalon else 'ОТЛИЧАЕТСЯ'))
    if sh and sh != etalon:
        for l in difflib.unified_diff(etalon.splitlines(), sh.splitlines(), lineterm='', n=0):
            print('   ' + l[:190])
    if s.endswith('0255010527'):
        m = re.search(r'<title>(.*?)</title>', o.text, re.S)
        print('   title: %s' % (m.group(1).strip() if m else '—'))
