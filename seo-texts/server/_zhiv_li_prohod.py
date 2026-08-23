# -*- coding: utf-8 -*-
r"""Жив ли прогон подписей и на чём он стоит."""
import json
import os
import subprocess
import time

d = {}
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*roli_telefonov*'} | "
     "%{ '{0}|{1}|{2}' -f $_.ProcessId, $_.CreationDate, $_.WorkingSetSize }"],
    capture_output=True, text=True, timeout=120)
d['процесс'] = [s.strip() for s in (out.stdout or '').splitlines() if s.strip()]
для = r'C:\sender\server\roli_telefonov.log'
if os.path.exists(для):
    d['лог_обновлён_мин_назад'] = int((time.time() - os.path.getmtime(для)) / 60)
    d['лог_байт'] = os.path.getsize(для)
ж = r'C:\sender\_ops\roli_telefonov.jsonl'
if os.path.exists(ж):
    d['журнал_обновлён_мин_назад'] = int((time.time() - os.path.getmtime(ж)) / 60)
    хв = [s.strip() for s in open(ж, encoding='utf-8', errors='replace') if s.strip()]
    d['журнал_хвост'] = [s[:150] for s in хв[-3:]]
# кто держит базу
out2 = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "%{ '{0}|{1}' -f $_.ProcessId, ($_.CommandLine -replace '.*\\\\','') }"],
    capture_output=True, text=True, timeout=120)
d['питоны'] = [s.strip()[:90] for s in (out2.stdout or '').splitlines()
               if s.strip()][:14]
print(json.dumps(d, ensure_ascii=False, indent=1)[:2500])
