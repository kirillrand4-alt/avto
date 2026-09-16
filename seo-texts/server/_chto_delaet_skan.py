# -*- coding: utf-8 -*-
"""Чем занят процесс скана: соединения, потоки, время CPU. Лог буферизован — смотрим по делу."""
import json
import subprocess

o = {}
ps = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$p = Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'}; "
     "$p | ForEach-Object { $pr = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; "
     "[pscustomobject]@{pid=$_.ProcessId; cpu=[math]::Round($pr.CPU,1); "
     "threads=$pr.Threads.Count; mb=[math]::Round($pr.WorkingSet64/1MB,1)} } | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=120)
o['процессы'] = (ps.stdout or ps.stderr or '').strip()[:400]

net = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$ids = (Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'}).ProcessId; "
     "Get-NetTCPConnection -OwningProcess $ids -ErrorAction SilentlyContinue | "
     "Group-Object State | Select-Object Name,Count | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=120)
o['соединения'] = (net.stdout or net.stderr or '').strip()[:400]

adr = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$ids = (Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'}).ProcessId; "
     "Get-NetTCPConnection -OwningProcess $ids -State Established -ErrorAction SilentlyContinue | "
     "Select-Object -First 8 RemoteAddress,RemotePort | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=120)
o['куда_стучится'] = (adr.stdout or adr.stderr or '').strip()[:500]

brow = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "(Get-Process chrome,chromium,msedge,firefox -ErrorAction SilentlyContinue | "
     "Measure-Object).Count"],
    capture_output=True, text=True, timeout=120)
o['браузерных_процессов'] = (brow.stdout or '').strip()[:40]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
