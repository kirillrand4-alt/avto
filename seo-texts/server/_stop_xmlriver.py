# -*- coding: utf-8 -*-
"""Остановить прогон xmlriver: классифицировать нечем, ретраи в 403 бессмысленны."""
import json, subprocess, time

r = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'} | ForEach-Object { "
     "$id=$_.ProcessId; $st=$_.CreationDate; "
     "[pscustomobject]@{pid=$id; start=$st} } | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o = {'было': (r.stdout or '').strip()[:300]}
# Гасим только тот, что запущен сегодня в 08:22 (xmlriver), не трогая прогон по лентам.
k = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*' -and "
     "$_.CreationDate -gt (Get-Date).AddMinutes(-40)} | "
     '%{ Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }'],
    capture_output=True, text=True, timeout=90)
o['погашено'] = [s.strip() for s in (k.stdout or '').split() if s.strip()]
time.sleep(3)
r2 = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'}).ProcessId | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o['осталось'] = (r2.stdout or '').strip()[:120]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
