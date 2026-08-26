# -*- coding: utf-8 -*-
"""Идут ли наши длинные прогоны и держат ли они sender.db."""
import subprocess

out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object { $_.CommandLine -like '*_ops*' } | "
     "ForEach-Object { $_.ProcessId.ToString() + ' | ' + $_.CreationDate + ' | ' + "
     "$_.CommandLine.Substring(0,[Math]::Min(130,$_.CommandLine.Length)) }"],
    capture_output=True, text=True, timeout=90)
print((out.stdout or "").strip()[:2000] or "прогонов из _ops нет")
