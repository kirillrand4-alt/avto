# -*- coding: utf-8 -*-
"""Снять ВСЕ прогоны генерации. Сводка в конце."""
import subprocess
import time


def список():
    вых = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*partiya_gen*' -or "
         "$_.CommandLine -like '*peregen*' -or "
         "$_.CommandLine -like '*regen_driver*' -or "
         "$_.CommandLine -like '*nochnoy_storozh*' } | "
         "ForEach-Object { \"$($_.ProcessId)|\" + "
         "$_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length)) }"],
        capture_output=True, text=True, timeout=90).stdout.strip()
    return [s for s in вых.splitlines() if s.strip()]


было = список()
for стр in было:
    пид = стр.split("|")[0].strip()
    if пид.isdigit():
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Stop-Process -Id %s -Force" % пид],
                       capture_output=True, text=True, timeout=60)
time.sleep(5)
стало = список()

# заодно снимаем расписание ночного сторожа, чтобы он не поднял прогон сам
задачи = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-ScheduledTask | Where-Object { $_.TaskName -like '*artiya*' -or "
     "$_.TaskName -like '*torozh*' -or $_.TaskName -like '*eyer*' } | "
     "ForEach-Object { \"$($_.TaskName) = $($_.State)\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

print("=" * 62)
print("=== СВОДКА: ОСТАНОВКА ПРОГОНОВ ===")
print("было запущено: %d" % len(было))
for с in было:
    print("   " + с[:130])
print("осталось живых: %d" % len(стало))
for с in стало:
    print("   " + с[:130])
print("")
print("=== ЗАДАЧИ РАСПИСАНИЯ, КОТОРЫЕ МОГУТ ПОДНЯТЬ ПРОГОН ===")
print(задачи if задачи else "   таких задач нет")
