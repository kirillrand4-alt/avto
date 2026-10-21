# -*- coding: utf-8 -*-
r"""fixSL (21.10): панель Meyer отвечает медленно (вход ~50 с, главная >90 с) – чем занята. Только чтение.

    python3 zapusk_na_servere.py fixSL_diag.py
"""
import os
import re
import subprocess
import time
import urllib.request


def zamer(url, t=60):
    t0 = time.time()
    try:
        k = urllib.request.urlopen(url, timeout=t).status
    except urllib.error.HTTPError as e:
        k = e.code
    except Exception as e:  # noqa: BLE001
        k = repr(e)[:60]
    return '%s за %.1f с' % (k, time.time() - t0)


o = subprocess.run('netstat -ano -p tcp', shell=True, capture_output=True, text=True).stdout
pid = next((l.split()[-1] for l in o.splitlines() if ':8016 ' in l and 'LISTEN' in l.upper()), None)
print('8016 PID', pid, '; соединений к 8016 ESTABLISHED:', sum(1 for l in o.splitlines() if re.search(r':8016\s+\S+\s+ESTABLISHED', l)),
      'CLOSE_WAIT:', sum(1 for l in o.splitlines() if ':8016 ' in l and 'CLOSE_WAIT' in l))
w = subprocess.run('wmic path Win32_PerfFormattedData_PerfProc_Process get Name,IDProcess,PercentProcessorTime,WorkingSetPrivate /format:csv',
                   shell=True, capture_output=True, text=True, errors='replace').stdout
rows = [l.split(',') for l in w.splitlines() if l.count(',') >= 4 and 'Node' not in l]
rows = sorted(rows, key=lambda r: -int(r[3]) if r[3].isdigit() else 0)[:12]
print('топ процессов по CPU (имя, pid, %CPU, память МБ):')
for r in rows:
    try:
        print('   %-28s %6s %4s%% %6d' % (r[2], r[1], r[3], int(r[4]) // 2**20))
    except Exception:  # noqa: BLE001
        pass
w = subprocess.run('wmic process where "name like \'python%\'" get ProcessId,ParentProcessId,CommandLine /format:list', shell=True,
                   capture_output=True, text=True, errors='replace').stdout
w = re.sub(r'(?i)(token|key|secret|password)\S*', '<скрыто>', w)
import sys
if '--kratko' in sys.argv:
    raise SystemExit(0)
print('\nпроцессы python:')
for blok in w.split('\n\n'):
    b = ' '.join(x.strip() for x in blok.splitlines() if x.strip())
    if b:
        print('   ' + b[:230])
for f in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
    for suf in ('', '-wal', '-shm', '-journal'):
        p = os.path.join(r'C:\centro2\data', f + suf)
        if os.path.exists(p):
            print('   %s: %.1f МБ, изменён %.0f с назад' % (f + suf, os.path.getsize(p) / 2**20, time.time() - os.path.getmtime(p)))
print('\nлокально /login:', zamer('http://127.0.0.1:8016/obzvon-meyer/centro/login'))
print('локально /centro (без входа):', zamer('http://127.0.0.1:8016/obzvon-meyer/centro'))
print('локально static css:', zamer('http://127.0.0.1:8016/obzvon-meyer/static/css/centro.css'))
