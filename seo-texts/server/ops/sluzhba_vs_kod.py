# -*- coding: utf-8 -*-
"""Когда запущена служба панели и когда менялись её модули: видит ли она свежий код."""
import os
import subprocess
import time

в = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -notlike '*server\\ops*' } | "
                    "ForEach-Object { \"$($_.ProcessId) $($_.CreationDate) $($_.CommandLine)\" }"],
                   capture_output=True, text=True, timeout=60).stdout
for с in в.splitlines():
    if с.strip():
        print("процесс:", с.strip()[:220])
for ф in ("confirm.py", "app.py", "ai_letter.py", "infopanel.py", "company_card.py"):
    for п in (os.path.join(r"C:\sender\sender", ф), os.path.join(r"C:\sender\sender\web", ф)):
        if os.path.exists(п):
            print("%-16s изменён %s" % (ф, time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(п)))))
print("=== СЛУЖБА VS КОД ===")
