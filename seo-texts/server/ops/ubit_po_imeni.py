# -*- coding: utf-8 -*-
"""Остановить python-процессы, в командной строке которых есть подстрока: ubit_po_imeni.py <подстрока>"""
import subprocess, sys
к = sys.argv[1]
в = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"], capture_output=True, text=True).stdout
for с in в.splitlines():
    if к in с and "ubit_po_imeni" not in с and "wmic" not in с:
        pid = с.split()[-1]
        if pid.isdigit():
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
            print("остановлен", pid, с.strip()[:150])
