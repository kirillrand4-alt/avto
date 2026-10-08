# -*- coding: utf-8 -*-
"""Какие базы РЕАЛЬНО открывает сервер копии — в процессе, запущенном как сервер.

Подозрение: «Статистика» через публичный адрес показала user1..user3 действующими и без
наших четверых, а в базе копии эти трое отключены. Значит часть кода копии читает не
свою базу. Все прежние проверки сами делали load_dotenv(.env) и поэтому этого не видели:
они проверяли окружение, которого у настоящего сервера нет.

Здесь .env НЕ подгружается: окружение ровно такое, с каким запускается uvicorn.
Плюс: не писала ли копия в боевую базу продаж с момента копирования.
"""
import io
import os
import re
import sqlite3
import subprocess
import sys

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'

if '--vnutri' not in sys.argv:
    # окружение — как у Popen сервера в моих скриптах перезапуска, без dotenv
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8', OBZVON_ROOT_PATH='/obzvon-meyer',
                 ENV_FILE=os.path.join(KOREN, '.env'))
    print('в окружении раннера: CENTRO_SALES_DB=%r CENTRIFUGAL_DB=%r PARK_PANEL_DB=%r'
          % (os.environ.get('CENTRO_SALES_DB'), os.environ.get('CENTRIFUGAL_DB'),
             os.environ.get('PARK_PANEL_DB')))
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'], capture_output=True,
                       timeout=900, cwd=KOREN, env=sreda)
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    if r.returncode:
        sys.stdout.write(r.stderr.decode('utf-8', 'replace')[-2500:])

    # ---- писала ли копия в боевую базу
    print()
    print('########## БОЕВАЯ БАЗА ПРОДАЖ: ЗАПИСИ ПОСЛЕ КОПИРОВАНИЯ (с 2026-10-07)')
    b = sqlite3.connect('file:%s?mode=ro' % r'C:\seostat\data\centro_sales.db', uri=True)
    b.row_factory = sqlite3.Row
    print('пользователи боевой: %s' % [(r['username'], r['is_active']) for r in b.execute(
        'select username, is_active from users order by username')])
    for r in b.execute("select action, username, count(*) n, min(created_at) s, max(created_at) po "
                       "from activity_log where created_at >= '2026-10-07' group by 1, 2"):
        print('   журнал: %s %s x%d  %s .. %s' % (r['action'], r['username'], r['n'], r['s'], r['po']))
    n = b.execute("select count(*) from activity_log where created_at >= '2026-10-07'").fetchone()[0]
    print('   записей журнала с 07.10: %d' % n)
    kol = [r[1] for r in b.execute('PRAGMA table_info(company_assignment)')]
    if 'assigned_at' in kol:
        for r in b.execute("select username, assigned_by, count(*) n, max(assigned_at) po "
                           "from company_assignment where assigned_at >= '2026-10-07' group by 1, 2"):
            print('   назначения с 07.10: %s (кем %s) x%d, последнее %s'
                  % (r['username'], r['assigned_by'], r['n'], r['po']))
        print('   назначений с 07.10: %d' % b.execute(
            "select count(*) from company_assignment where assigned_at >= '2026-10-07'").fetchone()[0])
    for t in ('company_state', 'company_comment'):
        pole = 'updated_at' if t == 'company_state' else 'created_at'
        print('   %s с 07.10: %d' % (t, b.execute(
            "select count(*) from %s where %s >= '2026-10-07'" % (t, pole)).fetchone()[0]))
    hk = [r[1] for r in b.execute('PRAGMA table_info(hidden_item)')]
    pole = 'created_at' if 'created_at' in hk else None
    if pole:
        print('   hidden_item с 07.10: %d' % b.execute(
            "select count(*) from hidden_item where created_at >= '2026-10-07'").fetchone()[0])
    print('   размер и время боевой базы: %d байт, изменена %s' % (
        os.path.getsize(r'C:\seostat\data\centro_sales.db'),
        __import__('time').strftime('%Y-%m-%d %H:%M', __import__('time').localtime(
            os.path.getmtime(r'C:\seostat\data\centro_sales.db')))))
    raise SystemExit(0)

# ======================================================== внутри: как сервер, без dotenv
os.chdir(KOREN)
sys.path.insert(0, KOREN)
import logging  # noqa: E402
import warnings  # noqa: E402
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
from app.obzvon import create_app  # noqa: E402,F401
from app.api import routes_park as rp  # noqa: E402
from app.services import centro_sales as cs  # noqa: E402
from app.config import get_settings  # noqa: E402

print('########## ПУТИ, КОТОРЫЕ ВИДИТ СЕРВЕР КОПИИ')
for imya in ('SALES_DB', 'CENTRO_DB', 'BAZA'):
    print('   routes_park.%-9s = %s' % (imya, getattr(rp, imya, '<нет>')))
s = get_settings()
for pole in ('centrifugal_db', 'centro_sales_db', 'database_url'):
    if hasattr(s, pole):
        print('   settings.%-16s = %s' % (pole, getattr(s, pole)))
# чем открывается база продаж в centro_sales
for imya in dir(cs):
    if re.search(r'path|PATH|DB', imya) and not imya.startswith('__'):
        v = getattr(cs, imya)
        if isinstance(v, (str, os.PathLike)) or callable(v) and 'path' in imya.lower():
            try:
                print('   centro_sales.%-20s = %s' % (imya, v() if callable(v) else v))
            except TypeError:
                pass
with cs.connect() as conn:
    f = conn.execute('PRAGMA database_list').fetchall()
    print('   centro_sales.connect() открывает: %s' % [x[2] for x in f])
    print('   пользователи там: %s' % [tuple(r) for r in conn.execute(
        'select username, is_active from users order by username')])

# откуда routes_park берёт пути и пишет ли
print()
print('########## routes_park.py: os.environ и запись')
t = io.open(os.path.join(KOREN, 'app', 'api', 'routes_park.py'), encoding='utf-8').read()
for i, l in enumerate(t.splitlines(), 1):
    if re.search(r'os\.environ|sqlite3\.connect\(|\.commit\(\)|sales\.connect\(|'
                 r'@router\.post|insert into|update company|INSERT INTO|UPDATE ', l):
        print('   %4d: %s' % (i, l.strip()[:150]))
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for fn in fajly:
        if fn.endswith('.py'):
            tt = io.open(os.path.join(kor, fn), encoding='utf-8', errors='replace').read()
            for m in re.finditer(r'os\.environ\.get\(\s*["\'](\w*(?:DB|_PATH|PARK)\w*)["\']\s*,\s*([^)]+)\)', tt):
                print('   %-28s %-18s по умолчанию %s' % (fn, m.group(1), m.group(2).strip()[:70]))
