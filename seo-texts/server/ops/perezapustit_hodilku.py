# -*- coding: utf-8 -*-
"""Снять ходилку и пустить её заново БЕЗ записи в базу (только журнал)."""
import os
import subprocess
import sys
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
КАТАЛОГ = r"C:\sender\_ops"
ЛИМ = sys.argv[1] if len(sys.argv) > 1 else "20000"
ПОТОК = sys.argv[2] if len(sys.argv) > 2 else "8"


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=90).stdout.strip()


было = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -like '*checko_finansy*' } | "
          "ForEach-Object { $_.ProcessId }").split()
for пид in было:
    if пид.isdigit():
        пш("Stop-Process -Id %s -Force" % пид)
time.sleep(4)

метка = time.strftime("%m%d-%H%M%S")
основа = os.path.join(КАТАЛОГ, "checko_finansy-%s" % метка)
лог, ош = основа + ".log", основа + ".err"
арг = [os.path.join(КАТАЛОГ, "checko_finansy.py"), "--lim", ЛИМ,
       "--potok", ПОТОК, "--bez-bazy"]
список = ", ".join("'" + a.replace("'", "''") + "'" for a in арг)
пш("$env:PYTHONIOENCODING='utf-8'; Start-Process -FilePath '%s' "
   "-ArgumentList %s -WindowStyle Hidden -RedirectStandardOutput '%s' "
   "-RedirectStandardError '%s'" % (ПИТОН, список, лог, ош))
time.sleep(30)

живые = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
           "Where-Object { $_.CommandLine -like '*checko_finansy*' } | "
           "ForEach-Object { $_.ProcessId }").split()
хвост = []
if os.path.exists(лог):
    хвост = open(лог, encoding="utf-8", errors="replace").read().splitlines()

print("=" * 70)
print("=== СВОДКА: ХОДИЛКА БЕЗ ЗАПИСИ В БАЗУ ===")
print("снято прежних: %s" % (", ".join(было) if было else "не было"))
print("пущено: checko_finansy.py --lim %s --potok %s --bez-bazy" % (ЛИМ, ПОТОК))
print("живых процессов: %s" % (", ".join(живые) if живые else "НЕТ"))
print("лог: %s" % лог)
print("")
print("=== ПЕРВЫЕ СТРОКИ ЛОГА ===")
for с in хвост[:12]:
    print("   " + с[:150])
