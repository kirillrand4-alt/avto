# -*- coding: utf-8 -*-
"""Только чтение: что за задача Storozh и какие питоны живы. Ничего не трогаем."""
import subprocess


def пш(ком, т=90):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                       capture_output=True, text=True, timeout=т)
    return (r.stdout or "").strip(), (r.stderr or "").strip()[:300]


задача, ош1 = пш(
    "Get-ScheduledTask -TaskName 'Storozh' -ErrorAction SilentlyContinue | "
    "ForEach-Object { \"state=$($_.State)  path=$($_.TaskPath)\" }")
действие, _ = пш(
    "(Get-ScheduledTask -TaskName 'Storozh' -ErrorAction SilentlyContinue)"
    ".Actions | ForEach-Object { \"$($_.Execute) $($_.Arguments)\" }")
триггер, _ = пш(
    "(Get-ScheduledTask -TaskName 'Storozh' -ErrorAction SilentlyContinue)"
    ".Triggers | ForEach-Object { $_.CimClass.CimClassName }")
питоны, _ = пш(
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "ForEach-Object { \"$($_.ProcessId)|\" + "
    "$_.CommandLine.Substring(0,[Math]::Min(130,$_.CommandLine.Length)) }")
служба, _ = пш("(Get-Service SenderPanel).Status")

print("=" * 62)
print("=== СВОДКА: ЧТО ЖИВО (только чтение) ===")
print("служба SenderPanel: %s" % (служба or "?"))
print("")
print("задача Storozh: %s" % (задача or "нет такой задачи"))
print("   что запускает: %s" % (действие or "?"))
print("   тип триггера:  %s" % (триггер or "?"))
if ош1:
    print("   ошибка чтения: %s" % ош1)
print("")
print("=== ЖИВЫЕ ПРОЦЕССЫ python.exe ===")
if питоны:
    for с in питоны.splitlines():
        print("   " + с[:140])
else:
    print("   ни одного")
