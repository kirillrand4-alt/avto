# -*- coding: utf-8 -*-
"""Диагностика: когда стартовал процесс панели и видит ли он новый код (только чтение).
Командную строку целиком не печатаем — только признаки (без секретов)."""
import datetime
import json
import os
import subprocess
import urllib.request

ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } | "
      "ForEach-Object { [pscustomobject]@{pid=$_.ProcessId; "
      "start=$_.CreationDate.ToString('yyyy-MM-dd HH:mm:ss'); cmd=$_.CommandLine} } | "
      "ConvertTo-Json")
out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                     capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
try:
    procs = json.loads(out or "[]")
    procs = procs if isinstance(procs, list) else [procs]
except Exception:  # noqa: BLE001
    procs = []
for p in procs:
    cmd = str(p.get("cmd") or "")
    if "sender" not in cmd.lower():
        continue
    признак = ("ПАНЕЛЬ (serve/static-dir)" if ("static-dir" in cmd or " serve" in cmd)
               else "другой процесс sender")
    модуль = cmd.split("-m ")[1].split()[0] if "-m " in cmd else os.path.basename(cmd.split()[1] if len(cmd.split()) > 1 else "?")
    print(f"pid={p['pid']} старт={p['start']} {признак} модуль={модуль}")
for ф in (r"C:\sender\sender\api\app.py", r"C:\sender\sender\confirm.py",
          r"C:\sender\sender\store.py", r"C:\sender\web\dist\index.html"):
    print("изменён:", ф, datetime.datetime.fromtimestamp(os.path.getmtime(ф)).strftime("%Y-%m-%d %H:%M:%S"))
print("сейчас:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
try:
    сх = json.loads(urllib.request.urlopen("http://127.0.0.1:8091/api/openapi.json", timeout=20).read())
    print("в живой службе есть /confirm/counts:", "/confirm/counts" in (сх.get("paths") or {}))
except Exception as e:  # noqa: BLE001
    print("openapi недоступен:", type(e).__name__, str(e)[:100])
print("=== ГОТОВО ===")
