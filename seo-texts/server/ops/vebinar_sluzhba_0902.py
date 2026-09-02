# -*- coding: utf-8 -*-
"""Только чтение: живёт ли служба отправки."""
import datetime as dt
import glob
import io
import os
import subprocess

print("=== ФАЙЛЫ ЛОГОВ ===")
пути = []
for шаб in (r"C:\sender\logs\*", r"C:\sender\*.log", r"C:\sender\log\*"):
    пути.extend(glob.glob(шаб))
for п in sorted(set(пути), key=lambda x: os.path.getmtime(x), reverse=True):
    if os.path.isfile(п):
        м = dt.datetime.fromtimestamp(os.path.getmtime(п))
        print("  %-38s %8d Б  изменён %s"
              % (os.path.basename(п), os.path.getsize(п), м.strftime("%m-%d %H:%M")))

print("\n=== ПРОЦЕССЫ PYTHON ===")
try:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\""
         " | Select-Object ProcessId,CreationDate,"
         "@{n='cl';e={$_.CommandLine.Substring(0,[Math]::Min(90,$_.CommandLine.Length))}}"
         " | Format-Table -AutoSize | Out-String -Width 200"],
        capture_output=True, text=True, timeout=60)
    print(out.stdout[:1800] or "(пусто)")
    if out.stderr.strip():
        print("  stderr: %s" % out.stderr[:200])
except Exception as ex:
    print("  не выполнить: %s" % str(ex)[:150])

print("\n=== ХВОСТ ГЛАВНОГО ЛОГА ОТПРАВКИ ===")
для = [п for п in пути if os.path.isfile(п)
       and any(k in os.path.basename(п).lower()
               for k in ("sender", "orchestr", "service", "sluzhba", "app"))]
для.sort(key=lambda x: os.path.getmtime(x), reverse=True)
if не_найден := (not для):
    print("  лога отправки среди файлов нет")
for п in для[:2]:
    м = dt.datetime.fromtimestamp(os.path.getmtime(п))
    print("  --- %s (изменён %s) ---" % (os.path.basename(п), м.strftime("%m-%d %H:%M")))
    строки = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for л in строки[-18:]:
        print("    " + л[:110])
