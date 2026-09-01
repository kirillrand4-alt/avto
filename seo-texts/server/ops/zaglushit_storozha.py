# -*- coding: utf-8 -*-
"""Выключить сторожа расписания и убедиться, что генерации нет вовсе."""
import subprocess
import time

def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True,
                          timeout=120).stdout.strip()

до = пш("Get-ScheduledTask -TaskName 'Storozh' | "
        "ForEach-Object { \"$($_.TaskName) state=$($_.State)\" }")
пш("Stop-ScheduledTask -TaskName 'Storozh' -ErrorAction SilentlyContinue")
пш("Disable-ScheduledTask -TaskName 'Storozh' -ErrorAction SilentlyContinue")
time.sleep(3)
после = пш("Get-ScheduledTask -TaskName 'Storozh' | "
           "ForEach-Object { \"$($_.TaskName) state=$($_.State)\" }")

# сам процесс сторожа, если он ещё крутится
сторож = пш(
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Where-Object { $_.CommandLine -like '*storozh*' } | "
    "ForEach-Object { $_.ProcessId }")
for пид in сторож.split():
    if пид.isdigit():
        пш("Stop-Process -Id %s -Force" % пид)
time.sleep(3)

остаток = пш(
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Where-Object { $_.CommandLine -like '*partiya_gen*' -or "
    "$_.CommandLine -like '*storozh*' -or $_.CommandLine -like '*peregen*' } | "
    "ForEach-Object { \"$($_.ProcessId)|\" + "
    "$_.CommandLine.Substring(0,[Math]::Min(110,$_.CommandLine.Length)) }")

все_задачи = пш(
    "Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' -and "
    "($_.TaskName -like '*artiya*' -or $_.TaskName -like '*torozh*' -or "
    "$_.TaskName -like '*eyer*' -or $_.TaskName -like '*gen*') } | "
    "ForEach-Object { \"$($_.TaskName) = $($_.State)\" }")

print("=" * 62)
print("=== СВОДКА: ГЕНЕРАЦИЯ ОСТАНОВЛЕНА ===")
print("сторож был:  %s" % (до or "нет такой задачи"))
print("сторож стал: %s" % (после or "нет такой задачи"))
print("процессы сторожа сняты: %s" % (сторож.replace("\n", ", ") or "не было"))
print("")
print("живых процессов генерации: %s" % (остаток or "НЕТ НИ ОДНОГО"))
print("")
print("оставшиеся включённые задачи расписания по генерации:")
print(все_задачи if все_задачи else "   нет ни одной")
