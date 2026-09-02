# -*- coding: utf-8 -*-
"""Перезапуск службы панели: оживает цикл автоотправки и подхватывается
правка auto_send.py. argv: проба | делать"""
import subprocess
import sys
import time

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
ПС = ["powershell", "-NoProfile", "-Command"]


def сп(к, таймаут=180):
    r = subprocess.run(ПС + [к], capture_output=True, text=True, timeout=таймаут)
    return (r.stdout or "").strip(), (r.stderr or "").strip()


было, _ = сп("Get-CimInstance Win32_Process -Filter \"Name like '%python%'\""
             " | Where-Object { $_.CommandLine -match 'serve-api' }"
             " | ForEach-Object { \"$($_.ProcessId) $($_.CreationDate)\" }")
print("процесс панели сейчас: %s" % (было or "не найден"))
сост, _ = сп("(Get-Service SenderPanel).Status")
print("служба SenderPanel: %s" % сост)

if not ДЕЛАТЬ:
    print("будет выполнено: Restart-Service SenderPanel")
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

out, err = сп("Restart-Service SenderPanel -Force; Start-Sleep -Seconds 12;"
              " (Get-Service SenderPanel).Status")
print("\nперезапуск: %s %s" % (out, err[:200]))
time.sleep(6)
стало, _ = сп("Get-CimInstance Win32_Process -Filter \"Name like '%python%'\""
              " | Where-Object { $_.CommandLine -match 'serve-api' }"
              " | ForEach-Object { \"$($_.ProcessId) $($_.CreationDate)\" }")
print("процесс панели после: %s" % (стало or "НЕ ПОДНЯЛСЯ"))
print("сменился: %s" % (было.split()[0] if было else "?") != (стало.split()[0] if стало else "?"))

здоровье, _ = сп("try { (Invoke-WebRequest -UseBasicParsing"
                 " -Uri 'http://127.0.0.1:8091/api/health' -TimeoutSec 10)"
                 ".StatusCode } catch { $_.Exception.Message }")
print("панель отвечает: %s" % здоровье[:120])
