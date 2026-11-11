# -*- coding: utf-8 -*-
"""Остановить фоновый прогон по имени скрипта (по умолчанию gaz_obrazcy): ostanovit_gaz_obrazcy.py [gen_gaz_kc]"""
import subprocess, sys
ИМЯ = sys.argv[1] if len(sys.argv) > 1 else "gaz_obrazcy"
в = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"], capture_output=True, text=True).stdout
убиты = []
for с in в.splitlines():
    if ИМЯ in с and "ostanovit" not in с and "wmic" not in с:
        pid = с.split()[-1]
        if pid.isdigit():
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True); убиты.append(pid)
print("остановлено:", убиты or "нечего")
