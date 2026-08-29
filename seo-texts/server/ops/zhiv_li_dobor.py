# -*- coding: utf-8 -*-
"""Жив ли отцеплённый добор и чем занят."""
import glob, io, os, subprocess, time
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*sdelki_dadata*' } | "
                    "Select-Object ProcessId,CreationDate | Format-List | Out-String"],
                   capture_output=True, text=True, timeout=90)
вывод = (r.stdout or r.stderr).strip()
print("процессы добора: %s" % (вывод or "НЕТ — прогон умер или закончился"))
for п in sorted(glob.glob(r"C:\sender\_ops\sdelki_dadata-*"))[-4:]:
    т = io.open(п, encoding="utf-8", errors="ignore").read()
    print("\n--- %s (%d б, изменён %s) ---"
          % (os.path.basename(п), len(т),
             time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))
    print(т[-300:] if т else "(пусто)")
print("\nсейчас: %s" % time.strftime("%H:%M:%S"))
