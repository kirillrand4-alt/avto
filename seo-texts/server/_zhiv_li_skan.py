# -*- coding: utf-8 -*-
"""Скан работает или висит: два замера CPU с паузой + стек по потокам."""
import json
import subprocess
import time

PS = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
      "Where-Object {$_.CommandLine -like '*news_scan*'} | ForEach-Object { "
      "$pr = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; "
      "[pscustomobject]@{pid=$_.ProcessId; cpu=[math]::Round($pr.CPU,2); "
      "threads=$pr.Threads.Count; mb=[math]::Round($pr.WorkingSet64/1MB,1); "
      "io=$pr.PagedMemorySize64} } | ConvertTo-Json -Compress")


def snimok():
    r = subprocess.run(['powershell', '-NoProfile', '-Command', PS],
                       capture_output=True, text=True, timeout=120)
    return (r.stdout or r.stderr or '').strip()


o = {'замер1': snimok()}
time.sleep(40)
o['замер2'] = snimok()
r = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$ids = (Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'}).ProcessId; "
     "Get-NetTCPConnection -OwningProcess $ids -ErrorAction SilentlyContinue | "
     "Select-Object State,RemoteAddress,RemotePort | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=120)
o['соединения'] = (r.stdout or '').strip()[:600]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
