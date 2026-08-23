# -*- coding: utf-8 -*-
r"""Как идёт слияние: лог, процесс, журнал."""
import json
import os
import subprocess
import time

d = {}
л = r'C:\sender\server\roli_sliyanie.log'
if os.path.exists(л):
    с = [x.strip() for x in open(л, encoding='utf-8', errors='replace') if x.strip()]
    d['лог'] = [x[:170] for x in с[-4:]]
    d['лог_обновлён_сек'] = int(time.time() - os.path.getmtime(л))
ж = r'C:\sender\_ops\roli_telefonov.jsonl'
if os.path.exists(ж):
    с = [x.strip() for x in open(ж, encoding='utf-8', errors='replace') if x.strip()]
    d['журнал'] = [x[:170] for x in с[-3:]]
    d['журнал_обновлён_сек'] = int(time.time() - os.path.getmtime(ж))
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*roli_telefonov*'} | "
     "%{ '{0}|{1}' -f $_.ProcessId, $_.CommandLine.Substring(0,60) }"],
    capture_output=True, text=True, timeout=90)
d['процесс'] = [s.strip() for s in (out.stdout or '').splitlines() if s.strip()]
print(json.dumps(d, ensure_ascii=False, indent=1)[:2000])
