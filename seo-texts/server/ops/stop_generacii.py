# -*- coding: utf-8 -*-
"""Остановить генерации (23.10: кончился баланс провайдера, все вызовы — 403):
STOP-файл дирижёру яруса C и снятие процессов python, в командной строке
которых есть одна из меток. Печатает, что снято.
    stop_generacii.py <метка,метка,...>"""
import io
import subprocess
import sys

io.open(r"C:\sender\_ops\v4c-pachki.STOP", "w").write("баланс провайдера 23.10")
метки = sys.argv[1].split(",")
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                   capture_output=True, text=True, timeout=120)
for s in r.stdout.splitlines():
    if "\t" not in s:
        continue
    pid, cmd = s.split("\t", 1)
    if any(м in cmd for м in метки):
        k = subprocess.run(["taskkill", "/PID", pid.strip(), "/F"], capture_output=True, text=True)
        print("снят", pid, cmd[-90:], "|", (k.stdout or k.stderr).strip()[:60])
