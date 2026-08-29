# -*- coding: utf-8 -*-
"""Кто держит enrich.db и живы ли прогоны добора."""
import glob, io, os, subprocess, time
print("=== процессы python ===")
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Select-Object ProcessId,CreationDate,"
                    "@{n='cmd';e={$_.CommandLine.Substring(0,"
                    "[Math]::Min(110,$_.CommandLine.Length))}} | Format-List | Out-String"],
                   capture_output=True, text=True, timeout=90)
print((r.stdout or r.stderr)[:1800])
print("=== файлы прогонов ===")
for п in sorted(glob.glob(r"C:\sender\_ops\sdelki_dadata-*")):
    print("   %-58s %8d б  %s"
          % (os.path.basename(п), os.path.getsize(п),
             time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))
for п in (r"C:\sender\enrich.db", r"C:\sender\_ops\sdelki-rekvizity.jsonl"):
    if os.path.exists(п):
        print("   %-58s %8.1f МБ %s"
              % (os.path.basename(п), os.path.getsize(п) / 1048576,
                 time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))
print("   сейчас на сервере: %s" % time.strftime("%H:%M:%S"))
