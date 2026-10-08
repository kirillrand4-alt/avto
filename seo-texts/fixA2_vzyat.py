# -*- coding: utf-8 -*-
"""Исправитель A2 (доводка вида карточки под новые данные контактов): только ЧТЕНИЕ.

Без аргументов (системный питон): кладёт на дроп `fixA2_kod.zip` (шаблоны, CSS/JS, web.py,
centro_catalog.py, routes_centro_sales.py, centro_sales.py, obzvon.py) и перезапускает
себя под venv с `--render`: рендер главной и карточек TestClient-ом на ВРЕМЕННОЙ копии
базы продаж -> `fixA2_html_<метка>.zip`; плюс выгрузка словарей контактов всех компаний
(как их отдаёт каталог карточке) -> `fixA2_kontakty.json` (только на дроп, не в репо).
Файлы панели не меняются, замок не нужен.

    python3 zapusk_na_servere.py fixA2_vzyat.py [метка] [ИНН ...]
"""
import io
import json
import os
import subprocess
import sys
import time
import zipfile

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
INN_PO_UMOLCH = ['5957004185', '4238013194', '5903154949', '6451402458']

if '--render' in sys.argv:
    i = sys.argv.index('--render')
    metka = sys.argv[i + 1]
    inny = sys.argv[i + 2:] or INN_PO_UMOLCH
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    TEST_DB = os.path.join(KOREN, '_bekap', 'fixA2-render-%s.db' % os.getpid())
    import sqlite3
    src = sqlite3.connect(os.environ['CENTRO_SALES_DB'])
    dst = sqlite3.connect(TEST_DB)
    src.backup(dst)
    src.close()
    dst.close()
    os.environ['CENTRO_SALES_DB'] = TEST_DB
    os.environ['PARK_OCHERED_SALES_DB'] = TEST_DB
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    out = os.path.join(DROP, 'fixA2_html_%s.zip' % metka)
    z = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED)
    for kto, u in (('admin', {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}),
                   ('sales', {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1})):
        vnutr.dependency_overrides[rcs.current_user] = (lambda u=u: u)
        with TestClient(vnutr) as kl:
            for imya, url in [('list', PUT + '/centro'), ('list100', PUT + '/centro?size=100')] + \
                    [('card_' + inn, PUT + '/centro?inn=' + inn) for inn in inny]:
                t0 = time.time()
                o = kl.get(url)
                print('%s %s %s %d знаков %.1f с' % (kto, imya, o.status_code, len(o.text), time.time() - t0))
                z.writestr('%s_%s.html' % (kto, imya), o.text)
    z.close()
    # словари контактов всех компаний – как их получает карточка
    try:
        from app.services import centro_catalog as cc
        import inspect
        imena = [n for n, f in vars(cc).items() if callable(f) and not n.startswith('__')]
        print('функции каталога: ' + ', '.join(sorted(imena))[:3000])
    except Exception as e:  # noqa: BLE001
        print('каталог: %r' % e)
    try:
        os.remove(TEST_DB)
    except OSError as e:
        print('копия не удалена: %s' % e)
    print('-> %s' % out)
    raise SystemExit(0)

metka = sys.argv[1] if len(sys.argv) > 1 else time.strftime('%H%M')
inny = sys.argv[2:]
out = os.path.join(DROP, 'fixA2_kod.zip')
z = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED)
n = 0
for d in (os.path.join(APP, 'templates'),):
    for f in os.listdir(d):
        p = os.path.join(d, f)
        if os.path.isfile(p):
            z.write(p, 'templates/' + f)
            n += 1
for koren, dirs, files in os.walk(os.path.join(APP, 'static')):
    dirs[:] = [x for x in dirs if x != 'dokaz']
    if 'dokaz' in koren:
        continue
    for f in files:
        if f.endswith(('.css', '.js')):
            p = os.path.join(koren, f)
            z.write(p, 'static/' + os.path.relpath(p, os.path.join(APP, 'static')).replace('\\', '/'))
            n += 1
for rel in ('web.py', r'services\centro_catalog.py', r'api\routes_centro_sales.py',
            r'api\routes_park.py', r'services\centro_sales.py', 'obzvon.py'):
    p = os.path.join(APP, rel)
    if os.path.exists(p):
        z.write(p, rel.replace('\\', '/'))
        n += 1
z.close()
print('файлов в архиве: %d -> %s' % (n, out))
zam = os.path.join(KOREN, '_zamok.txt')
print('замок: %s' % (io.open(zam, encoding='utf-8').read() if os.path.exists(zam) else 'свободен'))

sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
r = subprocess.run([VENV, os.path.abspath(__file__), '--render', metka] + inny,
                   capture_output=True, timeout=1500, cwd=KOREN, env=sreda)
sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-4000:])
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
