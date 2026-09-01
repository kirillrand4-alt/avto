# -*- coding: utf-8 -*-
"""Только про задачу Storozh: включена ли, что запускает, когда сработает."""
import subprocess


def пш(ком):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                       capture_output=True, text=True, timeout=90)
    return (r.stdout or "").strip()


состояние = пш(
    "Get-ScheduledTask -TaskName 'Storozh' -ErrorAction SilentlyContinue | "
    "ForEach-Object { \"state=$($_.State)\" }")
действие = пш(
    "(Get-ScheduledTask -TaskName 'Storozh' -ErrorAction SilentlyContinue)"
    ".Actions | ForEach-Object { \"$($_.Execute) $($_.Arguments)\" }")
инфо = пш(
    "Get-ScheduledTaskInfo -TaskName 'Storozh' -ErrorAction SilentlyContinue | "
    "ForEach-Object { \"следующий запуск: $($_.NextRunTime); последний: "
    "$($_.LastRunTime); итог: $($_.LastTaskResult)\" }")
прогоны = пш(
    "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Where-Object { $_.CommandLine -like '*partiya_gen*' }).Count")

print("=" * 62)
print("=== СВОДКА: СТОРОЖ ===")
print("состояние задачи Storozh: %s" % (состояние or "задачи нет"))
print("что запускает:            %s" % (действие or "?"))
print("%s" % (инфо or "сведений о запусках нет"))
print("живых прогонов partiya_gen: %s" % (прогоны or "0"))
