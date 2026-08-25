# -*- coding: utf-8 -*-
"""Остановить прогон генерации КЦ. Показать, что остановили.

Без --katit только показывает найденные процессы.
"""
import subprocess
import sys

КАТИТЬ = "--katit" in sys.argv
НАЙТИ = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         "Where-Object { $_.CommandLine -like '*partiya_gen.py*' } | "
         "Select-Object ProcessId,CreationDate,CommandLine | Format-List")
out = subprocess.run(["powershell", "-NoProfile", "-Command", НАЙТИ],
                     capture_output=True, text=True, timeout=90)
текст = (out.stdout or "").strip()
print(текст[:2500] or "прогонов partiya_gen не найдено")
if not КАТИТЬ:
    print("\nсухой прогон. Остановить: --katit")
    raise SystemExit(0)
СТОП = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "Where-Object { $_.CommandLine -like '*partiya_gen.py*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "
        "Write-Output ('остановлен ' + $_.ProcessId) }")
out2 = subprocess.run(["powershell", "-NoProfile", "-Command", СТОП],
                      capture_output=True, text=True, timeout=90)
print((out2.stdout or "").strip() or "нечего останавливать")
print((out2.stderr or "").strip()[:400])
