# -*- coding: utf-8 -*-
"""Почему панель тормозит: ошибки/блокировки в хвосте логов, нагрузка процессов, задержка API очереди."""
import io
import os
import subprocess
import time
import urllib.request
for п in (r"C:\sender\_ops\panel_err.log", r"C:\sender\_ops\panel_out.log"):
    with io.open(п, encoding="utf-8", errors="replace") as ф:
        ф.seek(max(0, os.path.getsize(п) - 400000))
        хв = ф.read().splitlines()
    плохие = [с for с in хв if any(к in с for к in ("Traceback", "locked", "Error", "ERROR", "Timeout", " 500 ", "WARNING"))]
    print("%s: проблемных строк в хвосте %d" % (п, len(плохие)))
    if плохие:
        i = max(i for i, с in enumerate(хв) if "Traceback" in с) if any("Traceback" in с for с in хв) else len(хв) - 1
        for с in хв[i:i + 14]:
            print("   ", с[:200])
print(subprocess.run(["powershell", "-NoProfile", "-Command",
      "Get-Process python* | Sort-Object CPU -Descending | Select-Object -First 6 Id,CPU,WorkingSet64,StartTime | Format-Table -AutoSize"],
      capture_output=True, text=True, timeout=60).stdout)
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
_к = Config.load(r"C:\sender\sender.yaml")
порт = _к.get("panel.port") or _к.get("server.port") or _к.get("api.port") or 8080
print("порт:", порт, subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-NetTCPConnection -State Listen | Where-Object OwningProcess -in (Get-Process python*).Id | Select-Object -ExpandProperty LocalPort) -join ','"], capture_output=True, text=True, timeout=60).stdout.strip())
for url in ("http://127.0.0.1:%s/api/confirm/groups" % порт, "http://127.0.0.1:%s/api/confirm/queue?limit=1" % порт):
    т = time.time()
    try:
        urllib.request.urlopen(url, timeout=120).read()
        print("%s: %.1f с" % (url, time.time() - т))
    except Exception as е:  # noqa: BLE001
        print("%s: %s за %.1f с" % (url, str(е)[:80], time.time() - т))
print("=== ПАНЕЛЬ ТОРМОЗИТ ===")
