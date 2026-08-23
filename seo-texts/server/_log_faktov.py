# -*- coding: utf-8 -*-
r"""Последние круги цикла фактов: где теряется скорость."""
import json
import os
import subprocess
import time

d = {}
л = r'C:\sender\server\fakty_cikl.log'
if os.path.exists(л):
    строки = [s.strip() for s in open(л, encoding='utf-8', errors='replace')
              if s.strip()]
    d['круги'] = [s[:230] for s in строки[-14:]]
    d['лог_обновлён_сек'] = int(time.time() - os.path.getmtime(л))
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*fakty_cikl*'} | "
     "%{ '{0}|{1}' -f $_.ProcessId, $_.CreationDate }"],
    capture_output=True, text=True, timeout=90)
d['процесс'] = [s.strip() for s in (out.stdout or '').splitlines() if s.strip()]
print(json.dumps(d, ensure_ascii=False, indent=1)[:3000])
