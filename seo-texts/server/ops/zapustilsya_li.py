# -*- coding: utf-8 -*-
"""Пустился ли отцеплённый прогон: процессы, свежие логи, хвост лога."""
import os
import subprocess
import time

КАТАЛОГ = r"C:\sender\_ops"

try:
    вых = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
         "ForEach-Object { \"$($_.ProcessId)  $($_.CreationDate)  \" + "
         "$_.CommandLine.Substring(0,[Math]::Min(160,$_.CommandLine.Length)) }"],
        capture_output=True, text=True, timeout=90).stdout.strip()
    print("=== ПРОЦЕССЫ partiya_gen ===")
    print(вых if вых else "   нет ни одного")
except Exception as ex:  # noqa: BLE001
    print("процессы не опросились: %s" % str(ex)[:90])

print("")
print("=== СВЕЖИЕ ЛОГИ partiya_gen-* ===")
файлы = []
for имя in os.listdir(КАТАЛОГ):
    if имя.startswith("partiya_gen-") and имя.endswith((".log", ".err")):
        п = os.path.join(КАТАЛОГ, имя)
        файлы.append((os.path.getmtime(п), п, os.path.getsize(п)))
файлы.sort(reverse=True)
for мт, п, рз in файлы[:6]:
    print("   %-52s %9d Б  %s" % (os.path.basename(п), рз,
                                  time.strftime("%d.%m %H:%M:%S",
                                                time.localtime(мт))))

if файлы:
    последний = None
    for мт, п, рз in файлы:
        if п.endswith(".log") and рз > 0:
            последний = п
            break
    if последний:
        print("")
        print("=== ХВОСТ %s ===" % os.path.basename(последний))
        with open(последний, "r", encoding="utf-8", errors="replace") as ф:
            стр = ф.read().splitlines()
        for s in стр[:34]:
            print("   " + s[:150])
        if len(стр) > 60:
            print("   ...")
            for s in стр[-26:]:
                print("   " + s[:150])
    for мт, п, рз in файлы[:3]:
        if п.endswith(".err") and рз > 0:
            print("")
            print("=== ОШИБКИ %s ===" % os.path.basename(п))
            with open(п, "r", encoding="utf-8", errors="replace") as ф:
                print("   " + "\n   ".join(ф.read().splitlines()[-20:]))
            break
