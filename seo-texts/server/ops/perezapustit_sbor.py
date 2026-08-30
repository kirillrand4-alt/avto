# -*- coding: utf-8 -*-
"""Перезапустить сбор с укороченным списком кодов.

daily_collect читает файл кодов ОДИН раз при старте, поэтому правка файла на
живом прогоне ничего не меняет — нужен перезапуск. CSV при этом не страдает:
сборщик докачивает в тот же файл и пропускает уже собранные компании.
"""
import io
import os
import subprocess
import sys
import time

КАТИТЬ = "--katit" in sys.argv
ИМЯ = "AgroOkvedCollectOnce"
BAT = r"C:\sender\_ops\sbor-agro.cmd"
ЛОГ = r"C:\sender\_ops\sbor-agro.log"
CSV = r"C:\seostat\Parser2\data\agro-base.csv"
КОДЫ = r"C:\seostat\Parser2\data\okved-agro.txt"

n = sum(1 for с in io.open(КОДЫ, encoding="utf-8") if с.strip())
строк = sum(1 for _ in io.open(CSV, encoding="utf-8", errors="ignore")) \
    if os.path.exists(CSV) else 0
print("кодов в файле сейчас: %d; в CSV собрано строк: %d" % (n, строк))
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*daily_collect*' } | "
                    "Select-Object ProcessId,CreationDate | Format-List | Out-String"],
                   capture_output=True, text=True, timeout=90)
print("живые прогоны:\n%s" % ((r.stdout or r.stderr).strip() or "нет"))

if not КАТИТЬ:
    print("[сухой прогон] с --katit сниму старый и запущу заново")
    raise SystemExit(0)

subprocess.run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                "Where-Object { $_.CommandLine -like '*daily_collect*' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
               capture_output=True, text=True, timeout=90)
time.sleep(3)
subprocess.run(["schtasks", "/End", "/TN", ИМЯ], capture_output=True,
               text=True, timeout=60)
r = subprocess.run(["schtasks", "/Run", "/TN", ИМЯ], capture_output=True,
                   text=True, timeout=60)
print("перезапуск (%s): %s" % (r.returncode, (r.stdout or r.stderr).strip()[:140]))
print("лог: %s" % ЛОГ)
