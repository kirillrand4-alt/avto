# -*- coding: utf-8 -*-
"""Только чтение: работает ли сбор Checko прямо сейчас."""
import subprocess

пс = ["powershell", "-NoProfile", "-Command"]
зпр = ("Get-CimInstance Win32_Process | Where-Object {"
       " $_.CommandLine -match 'checko|zenno' }"
       " | ForEach-Object { \"$($_.ProcessId) | $($_.CreationDate) | \""
       " + $_.CommandLine.Substring(0,[Math]::Min(90,$_.CommandLine.Length)) }")
out = subprocess.run(пс + [зпр], capture_output=True, text=True, timeout=90)
стр = (out.stdout or "").strip()
зпр2 = ("(Get-Process -Name ZennoPoster -ErrorAction SilentlyContinue"
        " | Measure-Object).Count")
out2 = subprocess.run(пс + [зпр2], capture_output=True, text=True, timeout=60)
print("=== ЗАПУЩЕНО СЕЙЧАС ===")
print(стр or "(процессов checko/zenno нет)")
print("  процессов ZennoPoster: %s" % (out2.stdout or "").strip())
