# -*- coding: utf-8 -*-
"""ЗАМОК на enrich.db: кто держит и как живые модули сервера с ним обходятся.

Ничего не пишет в существующие таблицы. Пробная запись идёт в СВОЮ временную таблицу
и тут же откатывается, чтобы измерить, доступна ли запись вообще.
"""
import glob
import io
import os
import re
import sqlite3
import time

BAZA = r'C:\sender\enrich.db'

print('размер базы: %d байт' % os.path.getsize(BAZA))
for f in ('enrich.db-wal', 'enrich.db-shm', 'enrich.db-journal'):
    p = os.path.join(r'C:\sender', f)
    print('  %s: %s' % (f, ('есть, %d байт' % os.path.getsize(p))
                        if os.path.exists(p) else 'нет'))

con = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
print('journal_mode (чтение): %s' % con.execute('pragma journal_mode').fetchone()[0])
print('page_size %s, sync %s' % (con.execute('pragma page_size').fetchone()[0],
                                 con.execute('pragma synchronous').fetchone()[0]))
con.close()

# как подключаются живые модули
obraz = re.compile(r'(sqlite3\.connect\([^\n]{0,120}|busy_timeout[^\n]{0,60}|'
                   r'journal_mode[^\n]{0,60}|PRAGMA[^\n]{0,60})', re.I)
vidno = 0
for f in sorted(glob.glob(r'C:\sender\*.py')):
    try:
        t = io.open(f, encoding='utf-8', errors='replace').read()
    except OSError:
        continue
    if 'enrich.db' not in t:
        continue
    naydeno = obraz.findall(t)
    if not naydeno:
        continue
    vidno += 1
    print('%s:' % os.path.basename(f))
    for x in sorted(set(naydeno))[:6]:
        print('    %s' % x.strip()[:104])
print('модулей, трогающих enrich.db: %d' % vidno)

# сколько ждать: пробуем взять запись с разной выдержкой
for vyderzhka in (5, 30, 120):
    t0 = time.time()
    try:
        c = sqlite3.connect(BAZA, timeout=vyderzhka)
        c.execute('create table if not exists proekt_proba_zamka (x)')
        c.execute('drop table proekt_proba_zamka')
        c.commit()
        c.close()
        print('ЗАПИСЬ ВЗЯТА при выдержке %d с (ждали %.1f с)' % (vyderzhka,
                                                                 time.time() - t0))
        break
    except sqlite3.OperationalError as e:
        print('выдержка %3d с: НЕ ВЗЯТА за %.1f с (%s)' % (vyderzhka, time.time() - t0,
                                                           str(e)[:60]))
        c.close() if 'c' in dir() else None

# кто из процессов держит файл
try:
    import subprocess
    r = subprocess.run(['powershell', '-Command',
                        "Get-Process python* -ErrorAction SilentlyContinue | "
                        "Select-Object -First 8 Id,ProcessName,StartTime | Format-Table"],
                       capture_output=True, text=True, timeout=60)
    print('процессы python:\n%s' % (r.stdout or r.stderr)[:600])
except Exception as e:  # noqa: BLE001
    print('процессы не посмотреть: %s' % str(e)[:80])
