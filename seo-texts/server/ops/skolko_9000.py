# -*- coding: utf-8 -*-
"""Сколько процессов partiya_gen живо (не должно быть двух прогонов разом)."""
import subprocess
в = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*partiya_gen.py*' } | "
                    "ForEach-Object { \"$($_.ProcessId) parent=$($_.ParentProcessId) $($_.CreationDate) $($_.CommandLine.Substring([Math]::Max(0,$_.CommandLine.Length-160)))\" }"],
                   capture_output=True, text=True, timeout=60).stdout
print(в.strip() or "нет")
print("=== СКОЛЬКО 9000 ===")
