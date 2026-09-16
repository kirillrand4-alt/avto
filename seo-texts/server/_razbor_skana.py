# -*- coding: utf-8 -*-
"""Жив ли скан на самом деле: командные строки, время старта, свежие файлы."""
import glob
import json
import os
import subprocess
import time

DIR = r'C:\sender\server'
o = {}

p = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Select-Object ProcessId,ParentProcessId,CreationDate,"
     "@{n='cl';e={$_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length))}} | "
     'ConvertTo-Json -Compress'],
    capture_output=True, text=True, timeout=120)
o['все_python'] = (p.stdout or '')[-2500:]

логи = sorted(glob.glob(os.path.join(DIR, 'news_scan_*.log')), key=os.path.getmtime)
if логи:
    st = os.stat(логи[-1])
    o['лог'] = {'файл': os.path.basename(логи[-1]), 'байт': st.st_size,
                'изменён': time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}

свежие = []
for путь in glob.glob(os.path.join(DIR, '*')):
    try:
        st = os.stat(путь)
    except OSError:
        continue
    if time.time() - st.st_mtime < 5400 and os.path.isfile(путь):
        свежие.append((time.strftime('%H:%M:%S', time.localtime(st.st_mtime)),
                       os.path.basename(путь), st.st_size))
o['файлы_за_последние_90_мин'] = sorted(свежие)[-25:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
