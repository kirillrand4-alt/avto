# -*- coding: utf-8 -*-
"""Какая служба каким процессом владеет + жив ли sverka_prigovorov."""
import sqlite3
import subprocess
import time

БАЗА = r"C:\sender\enrich.db"


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=120).stdout.strip()


службы = пш(
    "Get-CimInstance Win32_Service | Where-Object { $_.ProcessId -gt 0 } | "
    "ForEach-Object { \"$($_.Name)|PID $($_.ProcessId)|$($_.State)|\" + "
    "$_.PathName.Substring(0,[Math]::Min(70,$_.PathName.Length)) }")

сверка = пш(
    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
    "'*sverka_prigovorov*' -or $_.CommandLine -like '*sverka-prigovorov*' } | "
    "ForEach-Object { $мин = [int]((New-TimeSpan -Start $_.CreationDate "
    "-End (Get-Date)).TotalMinutes); \"PID $($_.ProcessId) работает $мин мин | \" "
    "+ $_.CommandLine.Substring(0,[Math]::Min(80,$_.CommandLine.Length)) }")

задача = пш(
    "Get-ScheduledTask -TaskName 'sender-sverka-prigovorov' | "
    "ForEach-Object { \"state=$($_.State)\" }")
инфо = пш(
    "Get-ScheduledTaskInfo -TaskName 'sender-sverka-prigovorov' | "
    "ForEach-Object { \"последний запуск $($_.LastRunTime), итог "
    "$($_.LastTaskResult), следующий $($_.NextRunTime)\" }")

# замок сейчас
t0 = time.time()
try:
    c = sqlite3.connect(БАЗА, timeout=10, isolation_level=None)
    c.execute("PRAGMA busy_timeout = 10000")
    c.execute("BEGIN IMMEDIATE")
    c.execute("ROLLBACK")
    c.close()
    замок = "СВОБОДЕН (взят за %.2f с)" % (time.time() - t0)
except Exception as ex:                                        # noqa: BLE001
    замок = "занят (%.1f с ожидания): %s" % (time.time() - t0, str(ex)[:50])

print("=" * 70)
print("=== СВОДКА: ВЛАДЕЛЬЦЫ И ЗАМОК ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("пишущий замок enrich.db: %s" % замок)
print("")
print("ЗАДАЧА sender-sverka-prigovorov: %s" % (задача or "?"))
print("   %s" % (инфо or "сведений нет"))
print("   процессы сверки: %s" % (сверка or "НЕТ НИ ОДНОГО"))
print("")
print("СЛУЖБЫ И ИХ ПРОЦЕССЫ (ищем владельцев job_runner, панели):")
интерес = ("sender", "enrich", "nssm", "pixel", "job")
for с in (службы or "").splitlines():
    if any(и in с.lower() for и in интерес):
        print("   " + с[:130])
