# -*- coding: utf-8 -*-
"""ТОЛЬКО ЧТЕНИЕ: кто сейчас пишет в enrich.db. Никого не снимаем."""
import subprocess
import time


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=90).stdout.strip()


сверка = пш(
    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
    "'*sverka_prigovorov*' } | ForEach-Object { $м = [int]((New-TimeSpan "
    "-Start $_.CreationDate -End (Get-Date)).TotalMinutes); "
    "\"PID $($_.ProcessId) работает $м мин\" }")
задача = пш("Get-ScheduledTask -TaskName 'sender-sverka-prigovorov' | "
            "ForEach-Object { \"state=$($_.State)\" }")

def цпу():
    д = {}
    for с in пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "ForEach-Object { \"$($_.ProcessId)=$([int](($_.UserModeTime + "
                "$_.KernelModeTime)/10000000))\" }").split():
        if "=" in с:
            п, в = с.split("=", 1)
            try:
                д[п] = int(в)
            except ValueError:
                pass
    return д

ц1 = цпу()
time.sleep(20)
ц2 = цпу()
имена = {}
for с in пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "ForEach-Object { \"$($_.ProcessId)|\" + "
            "$_.CommandLine.Substring(0,[Math]::Min(72,$_.CommandLine.Length)) }"
            ).splitlines():
    if "|" in с:
        п, к = с.split("|", 1)
        имена[п.strip()] = к.strip()

print("=" * 70)
print("=== СВОДКА: КТО СЕЙЧАС РАБОТАЕТ С БАЗОЙ ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("")
print("задача сверки приговоров: %s" % (задача or "?"))
print("   процесс сверки: %s" % (сверка or "НЕ ЗАПУЩЕН"))
print("")
print("процессорное время за 20 секунд:")
for д, п in sorted(((ц2.get(п, 0) - ц1.get(п, 0), п) for п in ц2), reverse=True)[:6]:
    if д > 0:
        print("   %-8s +%3d с  %s" % (п, д, имена.get(п, "?")[:80]))
