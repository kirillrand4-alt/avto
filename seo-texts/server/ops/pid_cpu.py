# -*- coding: utf-8 -*-
"""Процессор и память процесса: pid_cpu.py <pid>"""
import subprocess
import sys
print(subprocess.run(["powershell", "-NoProfile", "-Command",
                      "Get-Process -Id %s | Select-Object Id,CPU,WorkingSet64,StartTime | Format-List" % sys.argv[1]],
                     capture_output=True, text=True).stdout)
