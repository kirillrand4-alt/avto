# -*- coding: utf-8 -*-
r"""fixSL (21.10): поднять панель Meyer (порт 8016), если она не слушает: задача автозапуска, при неудаче – прямой запуск
zapusk.py (как в правилах перезапуска). Печатает, почему не поднялась (хвост вывода zapusk.py без секретов).

    python3 zapusk_na_servere.py fixSL_podnyat.py
"""
import os
import re
import subprocess
import time
import urllib.request

VENV = r'C:\seostat\.venv\Scripts\python.exe'
LOG = r'C:\centro2\_bekap\fixSL-zapusk-%s.log' % time.strftime('%Y%m%d-%H%M%S')


def pid_na(port):
    o = subprocess.run('netstat -ano -p tcp', shell=True, capture_output=True, text=True).stdout
    return next((l.split()[-1] for l in o.splitlines() if (':%d ' % port) in l and 'LISTEN' in l.upper()), None)


def login():
    t0 = time.time()
    try:
        k = urllib.request.urlopen('http://127.0.0.1:8016/obzvon-meyer/centro/login', timeout=120).status
    except Exception as e:  # noqa: BLE001
        k = repr(e)[:60]
    return '%s за %.1f с' % (k, time.time() - t0)


o = subprocess.run('wmic process where "name like \'python%\' and commandline like \'%zapusk.py%\'" get ProcessId,CommandLine /format:list',
                   shell=True, capture_output=True, text=True, errors='replace').stdout
print('процессы zapusk.py:', re.findall(r'ProcessId=(\d+)', o))
print('слушает 8016:', pid_na(8016))
if not pid_na(8016):
    for p in re.findall(r'ProcessId=(\d+)', o):
        subprocess.run('taskkill /PID %s /F /T' % p, shell=True, capture_output=True)
    f = open(LOG, 'w')
    subprocess.Popen([VENV, r'C:\centro2\zapusk.py'], cwd=r'C:\centro2', stdout=f, stderr=subprocess.STDOUT,
                     creationflags=0x00000008 | 0x00000200)
    for _ in range(60):
        time.sleep(3)
        if pid_na(8016):
            break
    print('после прямого запуска слушает 8016:', pid_na(8016))
    time.sleep(5)
    t = open(LOG, encoding='utf-8', errors='replace').read()
    t = re.sub(r'(?i)(secret|token|password|key)\S*\s*[=:]\s*\S+', r'\1=<скрыто>', t)
    print('хвост вывода zapusk.py:\n' + t[-1500:])
print('/login:', login())
print('/login ещё раз:', login())
