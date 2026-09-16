# -*- coding: utf-8 -*-
"""Как идёт скан: жив ли процесс, что в логе, сколько новых событий в базе."""
import glob
import json
import os
import sqlite3
import subprocess
import time

DIR = r'C:\sender\server'
o = {}

логи = sorted(glob.glob(os.path.join(DIR, 'news_scan_*.log')), key=os.path.getmtime)
o['лог'] = логи[-1] if логи else 'нет'
if логи:
    st = os.stat(логи[-1])
    o['лог_размер'] = st.st_size
    o['лог_обновлён_сек_назад'] = int(time.time() - st.st_mtime)
    with open(логи[-1], encoding='utf-8', errors='replace') as f:
        o['лог_хвост'] = f.read()[-1500:]

p = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'} | "
     'Select-Object ProcessId,WorkingSetSize | ConvertTo-Json -Compress'],
    capture_output=True, text=True, timeout=90)
o['процессы'] = (p.stdout or '').strip()[:300]

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=20)
o['сигналов_всего'] = c.execute('select count(*) from signals').fetchone()[0]
o['за_сегодня'] = c.execute(
    "select count(*) from signals where updated_at like ?", (time.strftime('%Y-%m-%d') + '%',)
).fetchone()[0]
c.close()

поток = os.path.join(DIR, 'news_stream.jsonl')
if os.path.exists(поток):
    st = os.stat(поток)
    o['поток_мб'] = round(st.st_size / 1048576, 2)
    o['поток_обновлён'] = time.strftime('%H:%M:%S', time.localtime(st.st_mtime))
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
