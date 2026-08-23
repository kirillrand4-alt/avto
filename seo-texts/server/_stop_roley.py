# -*- coding: utf-8 -*-
r"""Остановить застрявший прогон: он крутится на блокировках и держит процессор."""
import json
import subprocess

out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*roli_telefonov*'} | "
     '%{ Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }'],
    capture_output=True, text=True, timeout=120)
print(json.dumps({'погашено': [s.strip() for s in (out.stdout or '').split()
                               if s.strip()]}, ensure_ascii=False))
