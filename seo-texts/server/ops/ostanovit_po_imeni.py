# -*- coding: utf-8 -*-
"""Остановить все процессы python, в командной строке которых есть заданное имя скрипта.  ostanovit_po_imeni.py <имя.py> [--pid=N — только этот процесс]"""
import os, subprocess, sys
имя = sys.argv[1]
ПИД = next((a.split('=',1)[1] for a in sys.argv if a.startswith('--pid=')), None)
к = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*%s*' -and $_.ProcessId -ne %d -and $_.CommandLine -notlike '*ostanovit_po_imeni*'%s } "
     "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force; 'остановлен ' + $_.ProcessId }") % (имя, os.getpid(), (' -and $_.ProcessId -eq %d' % int(ПИД)) if ПИД else '')
print(subprocess.run(["powershell", "-NoProfile", "-Command", к], capture_output=True, text=True, errors="replace", timeout=60).stdout.strip() or "таких процессов нет")
