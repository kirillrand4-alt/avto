# -*- coding: utf-8 -*-
"""Файлы ошибок прогонов 24.08 и список живых python-процессов.

Оп нарочно короткий: панель отдаёт только хвост stdout, и длинный вывод
съедает как раз то, ради чего оп написан.
"""
import io
import os
import subprocess

КАТ = r"C:\sender\_ops"

print("=== ПРОЦЕССЫ PYTHON ===")
try:
    cmd = ('powershell -NoProfile -ExecutionPolicy Bypass -Command '
           '"Get-CimInstance Win32_Process -Filter \\"Name like \'python%\'\\" | '
           'ForEach-Object { \'{0} | {1}\' -f $_.ProcessId, '
           '$_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length)) }"')
    p = subprocess.run(cmd, shell=True, capture_output=True, timeout=60)
    print(((p.stdout or b"") + (p.stderr or b"")).decode("cp866", "replace").strip())
except Exception as e:                                         # noqa: BLE001
    print("ОШИБКА:", e)

print("\n=== ФАЙЛЫ ОШИБОК 24.08 ===")
for имя in sorted(os.listdir(КАТ)):
    if имя.startswith("partiya_gen-0824") and имя.endswith(".err"):
        п = os.path.join(КАТ, имя)
        текст = io.open(п, encoding="utf-8", errors="replace").read()
        print("\n---- %s (%d байт) ----" % (имя, os.path.getsize(п)))
        print(текст[-2000:])
