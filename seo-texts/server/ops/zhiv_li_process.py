# -*- coding: utf-8 -*-
"""Какие python-процессы живы и что в них за скрипт."""
import subprocess
ком = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
       "Select-Object ProcessId,CreationDate,CommandLine | Format-List")
r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                   capture_output=True, timeout=120)
т = (r.stdout or b"").decode("cp866", errors="replace")
if not т.strip():
    т = (r.stdout or b"").decode("utf-8", errors="replace")
print("=" * 70)
print("=== ЖИВЫЕ PYTHON-ПРОЦЕССЫ ===")
print(т[-3000:])
