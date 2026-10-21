# -*- coding: utf-8 -*-
r"""fixKC (21.10): панель КЦ (/obzvon/centro, порт 8012) – где код и базы, есть ли статистика, менеджеры, назначения и
активность. Только чтение, без телефонов и секретов.

    python3 zapusk_na_servere.py fixKC_razvedka.py
"""
import glob
import io
import os
import re
import sqlite3
import subprocess
import urllib.request

o = subprocess.run('wmic process where "commandline like \'%app.obzvon:app%--port 8012%\'" get ProcessId,ExecutablePath /format:list',
                   shell=True, capture_output=True, text=True, errors='replace').stdout
print('процесс 8012:', ' '.join(o.split())[:200])
for kor in (r'C:\seostat', r'C:\centro'):
    p = os.path.join(kor, 'app', 'api', 'routes_centro_sales.py')
    if os.path.exists(p):
        t = io.open(p, encoding='utf-8').read()
        print('\n%s: routes_centro_sales.py %d строк; маршрутов stats: %s; fixV/fixS/fixB есть: %s' % (
            kor, t.count('\n'), re.findall(r'@\w+\.get\("([^"]*stat[^"]*)"', t)[:5],
            [m for m in ('fixV', 'fixS', 'fixB', 'fixE2', 'centro_stats') if m in t]))
        tpl = os.path.join(kor, 'app', 'templates')
        print('   шаблоны со stat:', [f for f in os.listdir(tpl) if 'stat' in f.lower()])
        env = os.path.join(kor, '.env')
        if os.path.exists(env):
            print('   .env ключи с DB:', [l.split('=')[0] for l in io.open(env, encoding='utf-8', errors='replace') if 'DB' in l.split('=')[0]])
for put in glob.glob(r'C:\seostat\data\centro_sales*.db') + glob.glob(r'C:\centro\data\centro_sales*.db'):
    s = sqlite3.connect('file:%s?mode=ro' % put, uri=True)
    try:
        u = s.execute("SELECT username, role, is_active, COALESCE(fio,'') FROM users").fetchall()
    except sqlite3.OperationalError:
        u = s.execute("SELECT username, role, is_active FROM users").fetchall()
    print('\n%s (%.1f МБ): пользователи %s' % (put, os.path.getsize(put) / 2**20, u))
    try:
        print('   назначений:', s.execute('SELECT username, COUNT(*) FROM company_assignment GROUP BY 1').fetchall())
        print('   отметок (activity_log) за 30 дней:', s.execute(
            "SELECT username, COUNT(*), MAX(created_at) FROM activity_log WHERE created_at >= date('now','-30 day') GROUP BY 1").fetchall())
        print('   статусы company_state:', s.execute('SELECT username, COUNT(*) FROM company_state GROUP BY 1').fetchall())
    except sqlite3.OperationalError as e:
        print('   ', e)
for u in ('/obzvon/centro/login', '/obzvon/centro/stats'):
    try:
        k = urllib.request.urlopen('http://127.0.0.1:8012' + u, timeout=30).status
    except urllib.error.HTTPError as e:
        k = e.code
    except Exception as e:  # noqa: BLE001
        k = repr(e)[:60]
    print('8012 %s: %s' % (u, k))
