# -*- coding: utf-8 -*-
"""Как называются службы панели и в каком они состоянии."""
import subprocess

out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-Service | Where-Object { $_.Name -match 'sender|panel|pixel|drop' } | "
     "Select-Object Name,Status,StartType | Format-Table -AutoSize | "
     "Out-String -Width 100"],
    capture_output=True, text=True, timeout=60)
print((out.stdout or "").strip() or "служб не нашлось")
print("")
out2 = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Service | Where-Object { $_.Name -match 'sender|panel' } | "
     "ForEach-Object { $_.Name + ' | ' + $_.StartName + ' | ' + $_.PathName }"],
    capture_output=True, text=True, timeout=60)
print((out2.stdout or "").strip()[:900])
