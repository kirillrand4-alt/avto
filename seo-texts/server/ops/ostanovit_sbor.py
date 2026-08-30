# -*- coding: utf-8 -*-
"""Остановить прогон: он доедает последние ключи на коде, который мы убрали."""
import subprocess
import sys
КАТИТЬ = "--katit" in sys.argv
if not КАТИТЬ:
    print("[сухой] с --katit остановлю")
    raise SystemExit(0)
subprocess.run(["schtasks", "/End", "/TN", "AgroOkvedCollectOnce"],
               capture_output=True, text=True, timeout=60)
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*daily_collect*' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
                   capture_output=True, text=True, timeout=90)
print("остановлено: %s" % ((r.stdout or "").strip() or "нечего"))
