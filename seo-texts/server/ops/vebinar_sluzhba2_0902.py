# -*- coding: utf-8 -*-
"""Только чтение: ищем процесс отправщика среди всех python-процессов."""
import subprocess

пс = ("powershell", "-NoProfile", "-Command")
зпр = ("Get-CimInstance Win32_Process -Filter \"Name like '%python%'\""
       " | Where-Object { $_.CommandLine -match 'sender' } "
       " | ForEach-Object { \"$($_.ProcessId)|$($_.CreationDate)|\""
       " + $_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length)) }")
out = subprocess.run(list(пс) + [зпр], capture_output=True, text=True, timeout=60)
print("=== ПРОЦЕССЫ СО СЛОВОМ sender В КОМАНДНОЙ СТРОКЕ ===")
print(out.stdout.strip() or "(нет ни одного)")
if out.stderr.strip():
    print("stderr: %s" % out.stderr[:200])

зпр2 = ("Get-Service | Where-Object { $_.Name -match 'sender|otprav|mail' }"
        " | ForEach-Object { \"$($_.Name) = $($_.Status)\" }")
out2 = subprocess.run(list(пс) + [зпр2], capture_output=True, text=True, timeout=60)
print("\n=== СЛУЖБЫ WINDOWS ===")
print(out2.stdout.strip() or "(нет подходящих)")

зпр3 = ("Get-ScheduledTask | Where-Object { $_.TaskName -match 'sender|otprav|sluzhb' }"
        " | ForEach-Object { \"$($_.TaskName) = $($_.State)\" }")
out3 = subprocess.run(list(пс) + [зпр3], capture_output=True, text=True, timeout=60)
print("\n=== ЗАДАЧИ ПЛАНИРОВЩИКА ===")
print(out3.stdout.strip() or "(нет подходящих)")

зпр4 = ("Get-CimInstance Win32_Process -Filter \"Name like '%python%'\""
        " | Measure-Object | ForEach-Object { $_.Count }")
out4 = subprocess.run(list(пс) + [зпр4], capture_output=True, text=True, timeout=60)
print("\nвсего python-процессов: %s" % out4.stdout.strip())
