# -*- coding: utf-8 -*-
"""Какие python-процессы запущены с этим именем скрипта (только чтение).  kto_zapushchen.py <имя.py>"""
import subprocess, sys
к = "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*%s*' -and $_.CommandLine -notlike '*kto_zapushchen*' } | ForEach-Object { '{0} {1} {2}' -f $_.ProcessId, $_.CreationDate, ($_.CommandLine -replace '.*ops.', '').Substring(0, [Math]::Min(80, ($_.CommandLine -replace '.*ops.', '').Length)) }" % sys.argv[1]
print(subprocess.run(["powershell", "-NoProfile", "-Command", к], capture_output=True, text=True, errors="replace", timeout=60).stdout.strip() or "нет")
