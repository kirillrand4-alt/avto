# -*- coding: utf-8 -*-
"""Пустить поиск сайтов по мейеровским целям отцеплённо и надолго."""
import os
import subprocess
import sys
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
СКРИПТ = r"C:\sender\server\ops\sayty_dlya_celey.py"
ЦЕЛИ = r"C:\seostat\drop\celi_meyer_30mln.jsonl"
КАТАЛОГ = r"C:\sender\_ops"
ЛИМ = sys.argv[1] if len(sys.argv) > 1 else "5000"


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=90).stdout.strip()


было = пш("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine "
          "-like '*sayty_dlya_celey*' } | ForEach-Object { $_.ProcessId }").split()
for п in было:
    if п.isdigit():
        пш("Stop-Process -Id %s -Force" % п)
time.sleep(3)

метка = time.strftime("%m%d-%H%M%S")
основа = os.path.join(КАТАЛОГ, "poisk_saytov-%s" % метка)
лог, ош = основа + ".log", основа + ".err"
арг = [СКРИПТ, "--targets", ЦЕЛИ, "--lim", ЛИМ]
список = ", ".join("'" + a.replace("'", "''") + "'" for a in арг)
пш("$env:PYTHONIOENCODING='utf-8'; Start-Process -FilePath '%s' "
   "-ArgumentList %s -WindowStyle Hidden -RedirectStandardOutput '%s' "
   "-RedirectStandardError '%s'" % (ПИТОН, список, лог, ош))
time.sleep(25)

живые = пш("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine "
           "-like '*sayty_dlya_celey*' } | ForEach-Object { $_.ProcessId }").split()
хвост = []
if os.path.exists(лог):
    хвост = open(лог, encoding="utf-8", errors="replace").read().splitlines()

print("=" * 76)
print("=== СВОДКА: ПОИСК САЙТОВ ПУЩЕН ===")
print("снято прежних: %s" % (", ".join(было) if было else "не было"))
print("пущено: sayty_dlya_celey.py --targets %s --lim %s"
      % (os.path.basename(ЦЕЛИ), ЛИМ))
print("живых процессов: %s" % (", ".join(живые) if живые else "НЕТ"))
print("лог: %s" % лог)
print("")
for с in хвост[:12]:
    print("   " + с[:150])
