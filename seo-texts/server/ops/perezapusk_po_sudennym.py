# -*- coding: utf-8 -*-
"""Снять текущий прогон и пустить только по уже просуженным. Сводка в конце."""
import io
import json
import os
import subprocess
import sys
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
КАТАЛОГ = r"C:\sender\_ops"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ПОТОЛОК = sys.argv[1] if len(sys.argv) > 1 else "800"
СЕКУНД = sys.argv[2] if len(sys.argv) > 2 else "43200"


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=120).stdout.strip()


# что успел написать прежний прогон (журнал за последний час)
было_строк = 0
написано = 0
if os.path.exists(ЖУРНАЛ):
    порог = time.time() - 3600
    for стр in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        было_строк += 1
    # проще: смотрим время изменения файла
    свежий = os.path.getmtime(ЖУРНАЛ) > порог

пиды = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
          "ForEach-Object { $_.ProcessId }").split()
for пид in пиды:
    if пид.isdigit():
        пш("Stop-Process -Id %s -Force" % пид)
time.sleep(4)

метка = time.strftime("%m%d-%H%M%S")
основа = os.path.join(КАТАЛОГ, "partiya_gen-%s" % метка)
лог, ошибки = основа + ".log", основа + ".err"
арг = [os.path.join(КАТАЛОГ, "partiya_gen.py"), ПОТОЛОК, СЕКУНД,
       "meyer", "0", "модель=claude-sonnet-4-6", "--bez-predklassa",
       "--vyruchka-strogo", "--tolko-sudennye"]
список = ", ".join("'" + a.replace("'", "''") + "'" for a in арг)
пш("$env:PYTHONIOENCODING='utf-8'; Start-Process -FilePath '%s' "
   "-ArgumentList %s -WindowStyle Hidden -RedirectStandardOutput '%s' "
   "-RedirectStandardError '%s'" % (ПИТОН, список, лог, ошибки))
time.sleep(25)

живые = пш("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
           "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
           "ForEach-Object { $_.ProcessId }").split()
хвост = []
if os.path.exists(лог):
    хвост = io.open(лог, encoding="utf-8", errors="replace").read().splitlines()

print("=" * 64)
print("=== СВОДКА: ПЕРЕЗАПУСК ПО УЖЕ ПРОСУЖЕННЫМ ===")
print("снято прежних процессов: %s" % (", ".join(пиды) if пиды else "нечего"))
print("строк в журнале: %d; журнал трогали за последний час: %s"
      % (было_строк, "да" if свежий else "нет"))
print("")
print("пущено: potolok=%s секунд=%s meyer 0 sonnet "
      "--bez-predklassa --vyruchka-strogo --tolko-sudennye"
      % (ПОТОЛОК, СЕКУНД))
print("живых процессов: %s" % (", ".join(живые) if живые else "НЕТ"))
print("лог: %s" % лог)
print("")
print("=== ПЕРВЫЕ СТРОКИ ЛОГА ===")
for с in хвост[:26]:
    print("   " + с[:150])
