# -*- coding: utf-8 -*-
"""Состояние задания сбора и чистый перезапуск с паузой между запросами.

В логе: SSLError на api.checko.ru по шесть повторов подряд — сервер рвёт
соединения, когда в него долбят без пауз. Добавляем --delay и уменьшаем
одновременность.
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
КОРЕНЬ = r"C:\seostat\Parser2"

r = subprocess.run(["schtasks", "/Query", "/TN", ИМЯ, "/V", "/FO", "LIST"],
                   capture_output=True, text=True, timeout=60)
for с in (r.stdout or "").splitlines():
    if any(к in с for к in ("Status", "Last Run", "Last Result", "Состояние",
                            "Результат", "Next Run")):
        print("   %s" % с.strip()[:100])

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit пересоберу задание и запущу")
    raise SystemExit(0)

тело = (
    "@echo off\r\n"
    "cd /d %s\r\n" % КОРЕНЬ +
    ".venv\\Scripts\\python.exe scripts\\daily_collect.py "
    "--okved-file data\\okved-agro.txt --csv data\\agro-base.csv "
    "--no-contacts --main-okved-only --no-xlsx --no-key-check "
    "--delay 0.4 --concurrency 4 "
    ">> %s 2>&1\r\n" % ЛОГ)
with io.open(BAT, "w", encoding="utf-8", newline="") as f:
    f.write(тело)
    f.flush()
    os.fsync(f.fileno())
subprocess.run(["schtasks", "/End", "/TN", ИМЯ], capture_output=True,
               text=True, timeout=60)
subprocess.run(["schtasks", "/Delete", "/TN", ИМЯ, "/F"], capture_output=True,
               text=True, timeout=60)
когда = time.strftime("%H:%M", time.localtime(time.time() + 180))
r = subprocess.run(["schtasks", "/Create", "/TN", ИМЯ, "/SC", "ONCE",
                    "/ST", когда, "/RU", "SYSTEM", "/RL", "HIGHEST", "/F",
                    "/TR", BAT], capture_output=True, text=True, timeout=60)
print("создано (%s): %s" % (r.returncode, (r.stdout or r.stderr).strip()[:120]))
r = subprocess.run(["schtasks", "/Run", "/TN", ИМЯ], capture_output=True,
                   text=True, timeout=60)
print("запущено (%s): %s" % (r.returncode, (r.stdout or r.stderr).strip()[:120]))
time.sleep(20)
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*daily_collect*' } | "
                    "Select-Object ProcessId | Format-List | Out-String"],
                   capture_output=True, text=True, timeout=90)
print("процесс через 20 с: %s" % ((r.stdout or "").strip() or "НЕ ПОДНЯЛСЯ"))
