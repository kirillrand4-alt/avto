# -*- coding: utf-8 -*-
"""Все процессы python на сервере: PID, время старта, хвост командной строки.
Только чтение (секреты в командной строке не печатаем — режем по 'token'/'key')."""
import re
import subprocess

r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "ForEach-Object { \"$($_.ProcessId)`t$($_.CreationDate)`t$($_.CommandLine)\" }"],
                   capture_output=True, text=True, timeout=120)
for s in r.stdout.splitlines():
    if "\t" in s:
        pid, когда, cmd = (s.split("\t", 2) + ["", ""])[:3]
        cmd = re.sub(r"(?i)(token|key|pass)\S*", "***", cmd)
        print(pid, когда[:14], cmd[-150:])
