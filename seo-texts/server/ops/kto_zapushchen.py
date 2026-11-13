# -*- coding: utf-8 -*-
"""Какие python-процессы запущены с этим именем скрипта (только чтение).  kto_zapushchen.py <имя.py>"""
import subprocess, sys
к = "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*%s*' -and $_.CommandLine -notlike '*kto_zapushchen*' } | ForEach-Object { '{0} {1}' -f $_.ProcessId, $_.CreationDate }" % sys.argv[1]
print(subprocess.run(["powershell", "-NoProfile", "-Command", к], capture_output=True, text=True, errors="replace", timeout=60).stdout.strip() or "нет")
