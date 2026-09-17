# -*- coding: utf-8 -*-
"""Как идёт цепочка по RSS-донорам: процессы, логи, доноры, поток."""
import glob
import json
import os
import sqlite3
import subprocess
import time

DIR = r'C:\sender\server'
o = {'сейчас': time.strftime('%H:%M:%S')}

r = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*rss_cepochka*' -or $_.CommandLine -like '*news_scan*'} | "
     "ForEach-Object { $pr = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; "
     "[pscustomobject]@{pid=$_.ProcessId; cpu=[math]::Round($pr.CPU,1); "
     "mb=[math]::Round($pr.WorkingSet64/1MB,0)} } | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o['процессы'] = (r.stdout or '').strip()[:300]

for шаблон in ('rss_*.log', 'rss_cepochka_*.itog.json'):
    for путь in sorted(glob.glob(os.path.join(DIR, шаблон)), key=os.path.getmtime)[-3:]:
        st = os.stat(путь)
        зап = {'байт': st.st_size,
               'изменён': time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}
        if st.st_size and st.st_size < 4000:
            with open(путь, encoding='utf-8', errors='replace') as f:
                зап['текст'] = f.read()[-900:]
        elif st.st_size:
            with open(путь, encoding='utf-8', errors='replace') as f:
                зап['хвост'] = f.read()[-600:]
        o.setdefault('файлы', {})[os.path.basename(путь)] = зап

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
o['доноров_live_c_rss'] = c.execute(
    "select count(*) from donors where coalesce(rss,'')<>'' and status='live'").fetchone()[0]
o['доноров_без_отметки'] = c.execute(
    "select count(*) from donors where coalesce(status,'')=''").fetchone()[0]
o['сигналов'] = c.execute('select count(*) from signals').fetchone()[0]
c.close()

П = os.path.join(DIR, 'news_stream.jsonl')
o['поток'] = {'байт': os.path.getsize(П),
              'изменён': time.strftime('%H:%M:%S', time.localtime(os.stat(П).st_mtime))}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
