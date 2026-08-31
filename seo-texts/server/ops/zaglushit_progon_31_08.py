# -*- coding: utf-8 -*-
"""Остановить прогон partiya_gen (§7 Шаг 5). Письма в журнале сохраняются,
повторный запуск их не переписывает - резюм идёт по ИНН."""
import subprocess

найдено = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
     "Select-Object ProcessId,CommandLine | Format-List"],
    capture_output=True, text=True, timeout=90)
print("=== НАЙДЕНО ДО ОСТАНОВКИ ===")
print(найдено.stdout.strip()[:900] or "  ничего не идёт")

if "partiya_gen" in (найдено.stdout or ""):
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "
         "\"остановлен $($_.ProcessId)\" }"],
        capture_output=True, text=True, timeout=90)
    print("\n=== ОСТАНОВКА ===")
    print(r.stdout.strip()[:400] or r.stderr.strip()[:400])

проверка = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
     "Measure-Object | Select-Object -ExpandProperty Count"],
    capture_output=True, text=True, timeout=90)
print("\n=== ИТОГ ===")
print("  осталось процессов partiya_gen: %s" % (проверка.stdout or "?").strip())
