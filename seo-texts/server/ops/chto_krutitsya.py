# -*- coding: utf-8 -*-
"""Что сейчас крутится: процессы python и свежие логи прогонов."""
import os
import subprocess
import time

print("=== процессы python ===")
try:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         "Select-Object ProcessId,CreationDate,"
         "@{n='cmd';e={$_.CommandLine.Substring(0,[Math]::Min(150,$_.CommandLine.Length))}} | "
         "Format-List"],
        capture_output=True, text=True, timeout=60)
    print((out.stdout or "").strip()[:3000])
except Exception as e:
    print("не вышло: %r" % e)

print("")
print("=== свежие логи в C:\\sender\\_ops ===")
кат = r"C:\sender\_ops"
файлы = []
for имя in os.listdir(кат):
    п = os.path.join(кат, имя)
    if имя.endswith((".log", ".err")) and os.path.isfile(п):
        файлы.append((os.path.getmtime(п), имя, os.path.getsize(п)))
файлы.sort(reverse=True)
сейчас = time.time()
for мт, имя, рз in файлы[:14]:
    print("%-46s %8d б  %5.0f мин назад" % (имя, рз, (сейчас - мт) / 60.0))

print("")
for мт, имя, рз in файлы[:6]:
    if not имя.endswith(".log"):
        continue
    print("---- %s (хвост) ----" % имя)
    with open(os.path.join(кат, имя), "r", encoding="utf-8", errors="replace") as f:
        строки = f.readlines()[-6:]
    for с in строки:
        print("   " + с.rstrip()[:160])
