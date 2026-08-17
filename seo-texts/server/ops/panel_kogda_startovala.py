# -*- coding: utf-8 -*-
"""Работает ли панель на СВЕЖЕМ коде: время старта процесса против mtime файлов.

Питон читает модуль при старте процесса. Панель - служба, живущая сутками,
поэтому залитая правка не выполняется ни разу, пока службу не перезапустят
(грабли 17.08 с ops-скриптами; со службой то же самое, только незаметнее).

Прямой повод: замер показал, что фильтр «КЦ» ОБЯЗАН прятать письмо #527
(letter_division='meyer'), а владелец видит его в списке. Первый подозреваемый -
старый процесс.

Печатаем время старта каждого питон-процесса и mtime боевых файлов.

    python zapusk_svoego_skripta.py ops/panel_kogda_startovala.py
"""
import os
import subprocess
import sys
import time

ФАЙЛЫ = [r"C:\sender\sender\api\app.py", r"C:\sender\sender\confirm.py",
         r"C:\sender\sender\ai_letter.py", r"C:\sender\sender\ai_quota.py",
         r"C:\sender\sender\sender.py"]

print("=== боевые файлы ===")
сейчас = time.time()
for п in ФАЙЛЫ:
    try:
        м = os.path.getmtime(п)
        print(f"  {os.path.basename(п):<16} изменён "
              f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(м))} "
              f"({(сейчас - м) / 60:.0f} мин назад)")
    except Exception as ex:                                     # noqa: BLE001
        print(f"  {п}: {str(ex)[:80]}")

print("\n=== питон-процессы и время их старта ===")
try:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
         "Select-Object ProcessId,CreationDate,"
         "@{n='cmd';e={$_.CommandLine.Substring(0,[Math]::Min(150,"
         "$_.CommandLine.Length))}} | Format-List"],
        capture_output=True, text=True, timeout=120)
    print((out.stdout or "")[:6000])
    if out.stderr:
        print("STDERR:", (out.stderr or "")[:600])
except Exception as ex:                                         # noqa: BLE001
    print("не удалось опросить процессы:", str(ex)[:200])

print("\n=== службы, похожие на панель ===")
try:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Service | Where-Object {$_.Name -match 'sender|panel|nssm|uvicorn'}"
         " | Select-Object Name,Status | Format-Table -AutoSize"],
        capture_output=True, text=True, timeout=120)
    print((out.stdout or "")[:2500])
except Exception as ex:                                         # noqa: BLE001
    print("службы не опрошены:", str(ex)[:200])
