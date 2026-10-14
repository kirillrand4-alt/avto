# -*- coding: utf-8 -*-
"""fixV: только чтение. Разведка перед ролью «руководитель отдела продаж»: города и команды,
журнал отметок (кто нажал, за кого), переходы компаний между городами, версии sqlite/anyio/fastapi
в venv (копирование контекста в поток). Ничего не пишет."""
import collections
import json
import os
import sqlite3
import subprocess
import sys

VENV = r'C:\seostat\.venv\Scripts\python.exe'
if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:], capture_output=True, timeout=600,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    sys.stderr.write(r.stderr.decode('utf-8', 'replace')[-3000:])
    raise SystemExit(r.returncode)
import anyio  # noqa: E402
import fastapi  # noqa: E402
import inspect  # noqa: E402
print('sqlite', sqlite3.sqlite_version, 'python', sys.version.split()[0], 'anyio', getattr(anyio, '__version__', '?'),
      'fastapi', fastapi.__version__)
try:
    from anyio._backends import _asyncio as _aa
    src = inspect.getsource(_aa)
    print('anyio copy_context в потоках:', 'copy_context' in src)
except Exception as e:  # noqa: BLE001
    print('anyio src?', e)
B = r'C:\centro2\data\centro_sales_meyer1.db'
c = sqlite3.connect('file:%s?mode=ro' % B, uri=True)
c.row_factory = sqlite3.Row
gor = {r['username']: (r['gorod'] or '', r['role'], r['is_active']) for r in c.execute('select username, gorod, role, is_active from users')}
kom = collections.defaultdict(list)
for u, (g, rl, a) in sorted(gor.items()):
    if rl == 'sales' and a:
        kom[g].append(u)
print('команды по городу:', dict(kom))
vl = dict(c.execute('select inn, username from company_assignment').fetchall())
print('назначений:', len(vl), collections.Counter(gor.get(u, ('?',))[0] for u in vl.values()))
akt = collections.Counter()
za_drugogo = collections.Counter()
mezhgorod = collections.Counter()
for r in c.execute('select inn, username, action, payload_json, created_at from activity_log'):
    try:
        pl = json.loads(r['payload_json'] or '{}')
    except ValueError:
        pl = {}
    akt[(r['action'], r['username'])] += 1
    su = pl.get('state_user') if isinstance(pl, dict) else None
    if su and su != r['username']:
        za_drugogo[(r['action'], r['username'], su)] += 1
    if r['action'] == 'call_saved':
        kto = su or r['username']
        tek = vl.get(str(r['inn']))
        if tek and gor.get(kto, ('?',))[0] != gor.get(tek, ('?',))[0]:
            mezhgorod[(kto, tek)] += 1
print('журнал (действие, кто):', sorted(akt.items()))
print('нажал за другого:', sorted(za_drugogo.items()))
print('отметки, где город отметившего != город нынешнего владельца:', sorted(mezhgorod.items()))
st_chuzh = c.execute('select count(*) from company_state s join company_assignment a on a.inn=s.inn where a.username<>s.username').fetchone()[0]
print('строк company_state не нынешнего владельца:', st_chuzh)
print('комментарии по авторам:', c.execute('select username, count(*) from company_comment group by 1').fetchall())
print('zvonok_sobytie по state_user:', c.execute('select state_user, username, count(*) from zvonok_sobytie group by 1,2').fetchall())
print('скрыто компаний:', c.execute("select count(*) from hidden_item where kind='company'").fetchone()[0])
print('журнал reassign:', c.execute("select count(*) from activity_log where action='reassigned'").fetchone()[0])
