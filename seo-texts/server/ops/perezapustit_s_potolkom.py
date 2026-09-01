# -*- coding: utf-8 -*-
"""Снять текущий прогон и пустить заново с меньшим потолком.

Вердикты гейта лежат в sender.db/target_verdicts и переживают перезапуск,
поэтому окно нового прогона наберётся почти целиком из кэша.
Аргумент: <потолок> <секунды>. Сводка в конце.
"""
import os
import subprocess
import sys
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
КАТАЛОГ = r"C:\sender\_ops"
ПОТОЛОК = sys.argv[1] if len(sys.argv) > 1 else "1200"
СЕКУНД = sys.argv[2] if len(sys.argv) > 2 else "39000"

было = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
     "ForEach-Object { $_.ProcessId }"],
    capture_output=True, text=True, timeout=90).stdout.split()
for пид in было:
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Stop-Process -Id %s -Force" % пид],
                   capture_output=True, text=True, timeout=60)
time.sleep(4)

метка = time.strftime("%m%d-%H%M%S")
основа = os.path.join(КАТАЛОГ, "partiya_gen-%s" % метка)
лог, ошибки = основа + ".log", основа + ".err"
арг = [os.path.join(КАТАЛОГ, "partiya_gen.py"), ПОТОЛОК, СЕКУНД,
       "meyer", "0", "модель=claude-sonnet-4-6", "--bez-predklassa"]
список = ", ".join("'" + a.replace("'", "''") + "'" for a in арг)
ком = ("$env:PYTHONIOENCODING='utf-8'; "
       "Start-Process -FilePath '%s' -ArgumentList %s "
       "-WindowStyle Hidden -RedirectStandardOutput '%s' "
       "-RedirectStandardError '%s'" % (ПИТОН, список, лог, ошибки))
subprocess.run(["powershell", "-NoProfile", "-Command", ком], timeout=90)
time.sleep(6)

стало = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
     "ForEach-Object { $_.ProcessId }"],
    capture_output=True, text=True, timeout=90).stdout.split()

print("=" * 62)
print("=== СВОДКА: ПЕРЕЗАПУСК ===")
print("снято процессов: %s" % (", ".join(было) if было else "нечего"))
print("пущено: partiya_gen.py %s %s meyer 0 модель=claude-sonnet-4-6 "
      "--bez-predklassa" % (ПОТОЛОК, СЕКУНД))
print("живых процессов сейчас: %s" % (", ".join(стало) if стало else "НЕТ"))
print("лог: %s" % лог)
