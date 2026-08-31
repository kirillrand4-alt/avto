# -*- coding: utf-8 -*-
"""Немедленно остановить прогоны partiya_gen и показать, что он успел."""
import glob
import io
import os
import subprocess
import time

r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
                    "ForEach-Object { $id=$_.ProcessId; Stop-Process -Id $id -Force; "
                    "  \"убит $id\" }"],
                   capture_output=True, text=True, timeout=120)
print("остановка: %s" % ((r.stdout or "").strip() or "процессов не было"))
if (r.stderr or "").strip():
    print("stderr: %s" % (r.stderr or "").strip()[:200])

логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)[:2]
for п in логи:
    возраст = (time.time() - os.path.getmtime(п)) / 60.0
    print("\n-- %s (%.1f мин назад, %d Б)"
          % (os.path.basename(п), возраст, os.path.getsize(п)))
    с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for x in с[-14:]:
        print("   %s" % x[:150])

r2 = subprocess.run(["powershell", "-NoProfile", "-Command",
                     "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                     "Where-Object { $_.CommandLine -like '*partiya_gen*' }).Count"],
                    capture_output=True, text=True, timeout=90)
print("\n=== ИТОГ ===")
print("живых прогонов partiya_gen осталось: %s" % (r2.stdout or "").strip())
