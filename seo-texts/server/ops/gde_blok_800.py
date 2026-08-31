# -*- coding: utf-8 -*-
"""Что делает блок 800 прямо сейчас: размер лога, возраст, потребление."""
import glob
import io
import os
import subprocess
import time

логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)[:2]
for п in логи:
    print("%-34s %8d Б  изменён %.1f мин назад"
          % (os.path.basename(п), os.path.getsize(п),
             (time.time() - os.path.getmtime(п)) / 60.0))
свежий = логи[0] if логи else None
if свежий:
    с = io.open(свежий, encoding="utf-8", errors="replace").read().splitlines()
    print("\nстрок в логе: %d" % len(с))
    for x in с[-12:]:
        print("   %s" % x[:150])

r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
                    "ForEach-Object { \"pid=$($_.ProcessId) cpu=$($_.UserModeTime) "
                    "mem=$([math]::Round($_.WorkingSetSize/1MB)) МБ старт=$($_.CreationDate)\" }"],
                   capture_output=True, text=True, timeout=90)
print("\nпроцесс: %s" % (r.stdout or "нет").strip()[:200])

ош = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.err"),
            key=os.path.getmtime, reverse=True)[:1]
for п in ош:
    размер = os.path.getsize(п)
    print("\nфайл ошибок %s: %d Б" % (os.path.basename(п), размер))
    if размер:
        for x in io.open(п, encoding="utf-8",
                         errors="replace").read().splitlines()[-8:]:
            print("   %s" % x[:150])
