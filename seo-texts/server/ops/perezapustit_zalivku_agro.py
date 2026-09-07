# -*- coding: utf-8 -*-
"""Снять медленную заливку и пустить правленую. Прогон идемпотентный."""
import os
import subprocess
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
КАТАЛОГ = r"C:\sender\_ops"


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=90).stdout.strip()


было = пш("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine "
          "-like '*zalit_agro*' } | ForEach-Object { $_.ProcessId }").split()
for п in было:
    if п.isdigit():
        пш("Stop-Process -Id %s -Force" % п)
time.sleep(4)

метка = time.strftime("%m%d-%H%M%S")
основа = os.path.join(КАТАЛОГ, "zalit_agro_v_bazu-%s" % метка)
лог, ош = основа + ".log", основа + ".err"
арг = [os.path.join(КАТАЛОГ, "zalit_agro_v_bazu.py"), "--primenit"]
список = ", ".join("'" + a.replace("'", "''") + "'" for a in арг)
пш("$env:PYTHONIOENCODING='utf-8'; Start-Process -FilePath '%s' "
   "-ArgumentList %s -WindowStyle Hidden -RedirectStandardOutput '%s' "
   "-RedirectStandardError '%s'" % (ПИТОН, список, лог, ош))
time.sleep(20)

живые = пш("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine "
           "-like '*zalit_agro*' } | ForEach-Object { $_.ProcessId }").split()

print("=" * 74)
print("=== СВОДКА: ПЕРЕЗАПУСК ЗАЛИВКИ ===")
print("снято прежних: %s" % (", ".join(было) if было else "не было"))
print("живых сейчас:  %s" % (", ".join(живые) if живые else "НЕТ"))
print("лог: %s" % лог)
