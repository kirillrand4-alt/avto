# -*- coding: utf-8 -*-
"""Проба ходилки в ОДИН поток: дело в многопоточности или нет."""
import subprocess
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
П = r"C:\sender\_ops\checko_finansy.py"

# снимаем текущий прогон, чтобы не мешал
subprocess.run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | Where-Object { "
                "$_.CommandLine -like '*checko_finansy*' } | ForEach-Object { "
                "Stop-Process -Id $_.ProcessId -Force }"],
               capture_output=True, text=True, timeout=60)
time.sleep(3)

t0 = time.time()
r = subprocess.run([ПИТОН, П, "--lim", "12", "--potok", "1", "--mobilnye",
                    "--bez-bazy"],
                   capture_output=True, text=True, timeout=600,
                   encoding="utf-8", errors="replace")
print("=" * 78)
print("=== СВОДКА: ОДИН ПОТОК ===")
print("код возврата %s, время %.0f с" % (r.returncode, time.time() - t0))
print("")
for с in (r.stdout or "").splitlines():
    print("   " + с[:170])
if r.stderr:
    print("--- ошибки ---")
    for с in r.stderr.splitlines()[-10:]:
        print("   " + с[:170])
