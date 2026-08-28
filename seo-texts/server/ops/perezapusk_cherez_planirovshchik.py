# -*- coding: utf-8 -*-
"""Перезапуск панели через планировщик задач.

Прямой Popen не сработал: DETACHED_PROCESS отцепляет консоль, но не выводит
процесс из дерева службы — остановка панели убила его вместе с собой, PID
остался прежним. Планировщик запускает задание СВОИМ процессом, поэтому
переживает остановку панели. Задание одноразовое и удаляет себя само.
"""
import io
import os
import subprocess
import sys
import time

КАТИТЬ = "--katit" in sys.argv
ИМЯ = "SenderPanelRestartOnce"
СКРИПТ = r"C:\sender\_ops\perezapusk.ps1"
ИТОГ = r"C:\sender\_ops\perezapusk-itog.txt"

тело = (
    "$ErrorActionPreference='Continue'\n"
    "Restart-Service SenderPanel -Force\n"
    "Start-Sleep -Seconds 8\n"
    "$s = Get-Service SenderPanel\n"
    "$p = (Get-CimInstance Win32_Service -Filter \"Name='SenderPanel'\").ProcessId\n"
    "\"$(Get-Date -Format s) status=$($s.Status) pid=$p\" | "
    "  Out-File -Encoding utf8 '%s'\n"
    "schtasks /Delete /TN %s /F | Out-Null\n" % (ИТОГ, ИМЯ))
if os.path.exists(ИТОГ):
    os.remove(ИТОГ)

r = subprocess.run(["sc.exe", "queryex", "SenderPanel"], capture_output=True,
                   text=True, timeout=30)
pid_до = ""
for стр in (r.stdout or "").splitlines():
    if "PID" in стр:
        pid_до = стр.split(":")[-1].strip()
print("PID службы сейчас: %s" % pid_до)

if not КАТИТЬ:
    print("[сухой прогон] с --katit заведу разовое задание планировщика")
    raise SystemExit(0)

with io.open(СКРИПТ, "w", encoding="utf-8-sig", newline="\r\n") as f:
    f.write(тело)
    f.flush()
    os.fsync(f.fileno())
print("скрипт положен: %s" % СКРИПТ)

subprocess.run(["schtasks", "/Delete", "/TN", ИМЯ, "/F"],
               capture_output=True, text=True, timeout=60)
когда = time.strftime("%H:%M", time.localtime(time.time() + 90))
r = subprocess.run(
    ["schtasks", "/Create", "/TN", ИМЯ, "/SC", "ONCE", "/ST", когда,
     "/RU", "SYSTEM", "/RL", "HIGHEST", "/F",
     "/TR", 'powershell -NoProfile -ExecutionPolicy Bypass -File "%s"' % СКРИПТ],
    capture_output=True, text=True, timeout=60)
print("создание задания (код %s): %s"
      % (r.returncode, (r.stdout or r.stderr).strip()[:200]))
r = subprocess.run(["schtasks", "/Run", "/TN", ИМЯ], capture_output=True,
                   text=True, timeout=60)
print("немедленный запуск (код %s): %s"
      % (r.returncode, (r.stdout or r.stderr).strip()[:200]))
print("если немедленный запуск не пройдёт, задание сработает в %s" % когда)
