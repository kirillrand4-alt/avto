# -*- coding: utf-8 -*-
"""Остановить прогон предпросева."""
import subprocess
import sys

КАТИТЬ = "--katit" in sys.argv
НАЙТИ = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         "Where-Object { $_.CommandLine -like '*predprosev_meyer*' } | "
         "Select-Object ProcessId,CreationDate | Format-List")
out = subprocess.run(["powershell", "-NoProfile", "-Command", НАЙТИ],
                     capture_output=True, text=True, timeout=90)
print((out.stdout or "").strip()[:900] or "прогонов предпросева не найдено")
if not КАТИТЬ:
    print("\nсухой прогон. Остановить: --katit")
    raise SystemExit(0)
СТОП = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "Where-Object { $_.CommandLine -like '*predprosev_meyer*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "
        "Write-Output ('ostanovlen ' + $_.ProcessId) }")
out2 = subprocess.run(["powershell", "-NoProfile", "-Command", СТОП],
                      capture_output=True, text=True, timeout=90)
print((out2.stdout or "").strip() or "нечего останавливать")
