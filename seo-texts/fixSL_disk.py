# -*- coding: utf-8 -*-
r"""fixSL (21.10): нагрузка на диск сервера и время ответа панели Meyer после перезапуска. Только чтение.

    python3 zapusk_na_servere.py fixSL_disk.py
"""
import sqlite3
import subprocess
import time
import urllib.request

w = subprocess.run('typeperf "\\PhysicalDisk(_Total)\\% Disk Time" "\\PhysicalDisk(_Total)\\Avg. Disk Queue Length" '
                   '"\\PhysicalDisk(_Total)\\Disk Read Bytes/sec" "\\Memory\\Available MBytes" -sc 5', shell=True,
                   capture_output=True, text=True, errors='replace').stdout
print('диск (% времени, очередь, чтение байт/с), свободно памяти МБ:')
for l in w.splitlines()[2:8]:
    print('   ' + l)
t0 = time.time()
k = sqlite3.connect(r'file:C:\centro2\data\meyer_baza1.db?mode=ro', uri=True)
n = len(k.execute('SELECT * FROM company').fetchall())
print('\nпрямое чтение всех company (%d): %.1f с' % (n, time.time() - t0))
t0 = time.time()
n = k.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
print('count contact (%d): %.1f с' % (n, time.time() - t0))
for i in range(3):
    for u in ('/obzvon-meyer/centro/login', '/obzvon-meyer/static/css/centro.css'):
        t0 = time.time()
        try:
            kod = urllib.request.urlopen('http://127.0.0.1:8016' + u, timeout=90).status
        except Exception as e:  # noqa: BLE001
            kod = repr(e)[:50]
        print('%d %s: %s за %.1f с' % (i, u, kod, time.time() - t0))
