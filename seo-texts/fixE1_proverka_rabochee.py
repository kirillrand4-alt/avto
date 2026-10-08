# -*- coding: utf-8 -*-
r"""Исправитель E1: проверка фильтра «Сейчас рабочее время» после пересчёта поясов (только чтение).

Часы панели (rcs.datetime) подменяются на чт 08.10.2026 14:30 UTC: в Москве (UTC+3) 17:30 – рабочее,
в Самаре и Саратове (UTC+4) 18:30 – уже нет. Ожидание: Маслосырзавод Орловский (было «Орловка»,
UTC+3) и Саратовский МК (был пустой регион, UTC+3) из фильтра выпадают, московский Привопье остаётся.
TestClient на ВРЕМЕННОЙ копии базы продаж; каталог только читается.

    python3 zapusk_na_servere.py fixE1_proverka_rabochee.py
"""
import os
import re
import sqlite3
import subprocess
import sys

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
PUT = '/obzvon-meyer'

if os.path.normcase(sys.executable) != os.path.normcase(VENV):
    r = subprocess.run([VENV, os.path.abspath(__file__)], capture_output=True, timeout=1200, cwd=KOREN,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5000:])
    sys.stdout.write(r.stderr.decode('utf-8', 'replace')[-1500:] if r.returncode else '')
    raise SystemExit(r.returncode)

sys.path.insert(0, KOREN)
import zapusk  # noqa: F401,E402
import datetime as _dt  # noqa: E402
import logging  # noqa: E402
import types  # noqa: E402
import warnings  # noqa: E402
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
for f in os.listdir(os.path.join(KOREN, '_bekap')):
    if f.startswith('fixE1-proverka-') and f.endswith('.db'):
        try:
            os.remove(os.path.join(KOREN, '_bekap', f))
        except OSError:
            pass
TEST_DB = os.path.join(KOREN, '_bekap', 'fixE1-proverka-%s.db' % os.getpid())
src = sqlite3.connect(os.environ['CENTRO_SALES_DB'])
dst = sqlite3.connect(TEST_DB)
src.backup(dst)
src.close()
dst.close()
os.environ['CENTRO_SALES_DB'] = TEST_DB
os.environ['PARK_OCHERED_SALES_DB'] = TEST_DB
from app.api import routes_centro_sales as rcs  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SEYCHAS = _dt.datetime(2026, 10, 8, 14, 30)


class Chasy(_dt.datetime):
    @classmethod
    def utcnow(cls):
        return SEYCHAS


rcs.datetime = types.SimpleNamespace(**{k: getattr(_dt, k) for k in dir(_dt) if not k.startswith('__')})
rcs.datetime.datetime = Chasy

k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
rows = [dict(r) for r in k.execute('select inn, predpriyatie, region, chas_poyas, region_ishodnyy from company')]
skrytye = set(rcs.sales.hidden_companies() or ())
ozhid = sum(1 for r in rows if r['inn'] not in skrytye and rcs._rabochee_vremya(r))
# как было бы со старыми поясами: 13 компаний с пустым/нераспознанным регионом шли по Москве (UTC+3)
staroe = sum(1 for r in rows if r['inn'] not in skrytye and rcs._rabochee_vremya(
    dict(r, chas_poyas=3 if r['inn'] in ('6381022763', '6453143086') else r['chas_poyas'])))
plohih = 0


def chislo(t):
    m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
    return int(m.group(1)) if m else -1


vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
print('часы панели: %s UTC (Москва %s, Самара %s)' % (
    SEYCHAS.strftime('%a %H:%M'), (SEYCHAS + _dt.timedelta(hours=3)).strftime('%H:%M'),
    (SEYCHAS + _dt.timedelta(hours=4)).strftime('%H:%M')))
with TestClient(vnutr) as kl:
    o = kl.get(PUT + '/centro', params={'rabochee': '1'})
    n = chislo(o.text)
    ok = o.status_code == 200 and n == ozhid
    plohih += not ok
    print('   %s «Сейчас рабочее время»: на странице %d, по поясам базы %d (со старыми поясами было бы %d)' % (
        'ОК ' if ok else 'ПЛОХО', n, ozhid, staroe))
    for q, nado in (('ОРЛОВСКИЙ', 0), ('САРАТОВСКИЙ МОЛОЧНЫЙ', 0), ('ПРИВОПЬЕ', 1)):
        bez = chislo(kl.get(PUT + '/centro', params={'q': q}).text)
        s = chislo(kl.get(PUT + '/centro', params={'q': q, 'rabochee': '1'}).text)
        ok = bez >= 1 and s == nado
        plohih += not ok
        print('   %s «%s»: без фильтра %d, с «Сейчас рабочее время» %d (ожидание %d)' % ('ОК ' if ok else 'ПЛОХО', q, bez, s, nado))
try:
    os.remove(TEST_DB)
except OSError:
    pass
print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
raise SystemExit(1 if plohih else 0)
