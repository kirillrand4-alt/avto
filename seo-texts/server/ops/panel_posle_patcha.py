# -*- coding: utf-8 -*-
"""Поднялась ли панель после перезапуска и подхватила ли правки."""
import io
import os
import subprocess
import time

ИТОГ = r"C:\sender\_ops\perezapusk-itog.txt"
print("=== ИТОГ ПЕРЕЗАПУСКА ===")
for круг in range(12):
    if os.path.exists(ИТОГ):
        print("   %s" % io.open(ИТОГ, encoding="utf-8",
                                errors="replace").read().strip())
        break
    time.sleep(5)
else:
    print("   файл итога не появился")

r = subprocess.run(["sc.exe", "queryex", "SenderPanel"], capture_output=True,
                   text=True, timeout=30)
for с in (r.stdout or "").splitlines():
    if any(к in с for к in ("STATE", "PID")):
        print("   %s" % с.strip())

print("\n=== ОТВЕЧАЕТ ЛИ ПАНЕЛЬ ===")
r2 = subprocess.run(["powershell", "-NoProfile", "-Command",
                     "try { (Invoke-WebRequest -Uri "
                     "'http://127.0.0.1:8091/healthz' -UseBasicParsing "
                     "-TimeoutSec 10).StatusCode } catch { $_.Exception.Message }"],
                    capture_output=True, text=True, timeout=60)
print("   /healthz: %s" % (r2.stdout or r2.stderr).strip()[:120])

print("\n=== ПРАВКИ В ЖИВОМ ФАЙЛЕ ===")
т = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8").read()
for метка, кусок in (
        ("ручное письмо заводит messages", "_mid_ruchnogo"),
        ("ответ в ветке уходит сразу", "otpravleno")):
    print("   %-34s %s" % (метка, "есть" if кусок in т else "НЕТ"))
print("   строк в файле: %d" % len(т.splitlines()))

print("\n=== ЖУРНАЛ ПАНЕЛИ, ПОСЛЕДНИЕ СТРОКИ ===")
for п in (r"C:\sender\_ops\panel_out.log", r"C:\sender\panel_out.log"):
    if os.path.exists(п):
        с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
        for x in с[-8:]:
            print("   %s" % x[:150])
        break
