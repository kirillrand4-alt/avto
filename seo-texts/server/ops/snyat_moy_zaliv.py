# -*- coding: utf-8 -*-
"""Снять МОЙ зависший процесс заливки. Чужие пишущие опы не трогаем."""
import subprocess
import time


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=90).stdout.strip()


мои = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*zalit_kody_v_requisites*' } | "
         "ForEach-Object { $_.ProcessId }").split()
for пид in мои:
    if пид.isdigit():
        пш("Stop-Process -Id %s -Force" % пид)
time.sleep(3)

осталось = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
              "Where-Object { $_.CommandLine -like '*zalit_kody*' } | "
              "ForEach-Object { $_.ProcessId }").split()
чужие = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
           "Where-Object { $_.CommandLine -like '*sverka_prigovorov*' -or "
           "$_.CommandLine -like '*enrich_contacts*' } | "
           "ForEach-Object { \"$($_.ProcessId)|\" + "
           "$_.CommandLine.Substring(0,[Math]::Min(80,$_.CommandLine.Length)) }")

print("=" * 68)
print("=== СВОДКА ===")
print("снято моих процессов заливки: %s" % (", ".join(мои) if мои else "не было"))
print("осталось моих: %s" % (", ".join(осталось) if осталось else "ни одного"))
print("")
print("ЧУЖИЕ ПИШУЩИЕ ОПЫ (не трогал):")
for с in (чужие or "нет таких").splitlines():
    print("   " + с[:96])
