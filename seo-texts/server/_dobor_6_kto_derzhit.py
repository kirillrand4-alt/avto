# -*- coding: utf-8 -*-
"""Кто держит запись в enrich.db: размер WAL, пробная запись, активные процессы."""
import json
import os
import sqlite3
import subprocess
import time

BD = r'C:\sender\enrich.db'
for p in (BD, BD + '-wal', BD + '-shm'):
    if os.path.exists(p):
        print(os.path.basename(p), '%.1f МБ' % (os.path.getsize(p) / 2 ** 20),
              time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(p))))

# пробуем взять запись на 5 секунд — БЕЗ изменения данных (сразу откат)
t0 = time.time()
try:
    c = sqlite3.connect(BD, timeout=5)
    c.execute('PRAGMA busy_timeout=5000')
    c.execute('BEGIN IMMEDIATE')
    c.execute('ROLLBACK')
    print('запись доступна, взял за %.1f сек' % (time.time() - t0))
    c.close()
except Exception as e:  # noqa: BLE001
    print('запись НЕ доступна за %.1f сек: %s' % (time.time() - t0, str(e)[:90]))

print('--- лог добора ---')
t = open(r'C:\sender\_tmp\kesh-dobor.out', encoding='utf-8', errors='replace').read()
print(t[-900:])
try:
    out = subprocess.run(['wmic', 'process', 'where', "name='python.exe'",
                          'get', 'ProcessId,CommandLine'], capture_output=True,
                         text=True, timeout=60).stdout
    for s in out.splitlines():
        s = s.strip()
        if any(k in s for k in ('fakty_cikl', 'zenno_most', 'roli_telefonov',
                                'dobor', 'obzvon', 'merge', 'enrich_contacts')):
            print('ПРОЦ:', s[:130])
except Exception as e:  # noqa: BLE001
    print('процессы:', str(e)[:80])
