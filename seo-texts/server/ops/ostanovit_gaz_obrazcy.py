# -*- coding: utf-8 -*-
"""Остановить фоновый прогон gaz_obrazcy.py (только его; по командной строке процесса)."""
import subprocess
в = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"], capture_output=True, text=True).stdout
убиты = []
for с in в.splitlines():
    if "gaz_obrazcy" in с and "ostanovit" not in с and "wmic" not in с:
        pid = с.split()[-1]
        if pid.isdigit():
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True); убиты.append(pid)
print("остановлено:", убиты or "нечего")
