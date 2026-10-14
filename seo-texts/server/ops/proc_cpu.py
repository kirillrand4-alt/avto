# -*- coding: utf-8 -*-
"""CPU и потоки процесса: proc_cpu.py <pid>"""
import subprocess
import sys
print(subprocess.run(["powershell", "-NoProfile", "-Command",
                      "Get-Process -Id %s | Select-Object Id,CPU,Threads,WorkingSet64,StartTime | Format-List; "
                      "Get-NetTCPConnection -OwningProcess %s -ErrorAction SilentlyContinue | Group-Object State | Select Name,Count"
                      % (sys.argv[1], sys.argv[1])], capture_output=True, text=True, timeout=60).stdout)
print("=== CPU ===")
