# -*- coding: utf-8 -*-
"""Снять вставшие прогоны партии и пустить их заново с чинёным гейтом.

Прогоны 24.08 в 10:33/10:34 простояли час в гейте адресата и не выдали
ни одного письма: линза уходила на запасную opus-4-7, а та отвечает за
106 секунд при заслоне молчащего стрима в ~100. Замер того же часа:
sonnet-4-6 — 18 с, opus-4-8 — 36 с, opus-4-7 — 106 с. Гейт ставим на
sonnet (он и вдвое быстрее, и впятеро дешевле), письма остаются на
opus-4-8 по слову владельца.

Кэш вердиктов гейта durable (таблица target_verdicts), поэтому всё, что
успели осудить, при перезапуске не теряется.
"""
import os
import subprocess
import sys
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
КАТАЛОГ = r"C:\sender\_ops"
СКРИПТ = os.path.join(КАТАЛОГ, "partiya_gen.py")

ОБЩЕЕ = ["--bez-zacepki", "--bez-predklassa", "porog=1.5",
         "gate_model=claude-sonnet-4-6", "zapas=claude-sonnet-4-6",
         "gate_threads=8"]
ПРОГОНЫ = [["500", "14400", "kc", "1"] + ОБЩЕЕ,
           ["200", "10800", "meyer", "1"] + ОБЩЕЕ]

print("=== СНИМАЮ ВСТАВШИЕ ПРОГОНЫ ===")
вывод = subprocess.run(
    ["wmic", "process", "where", "name='python.exe'",
     "get", "ProcessId,CommandLine", "/format:list"],
    capture_output=True, text=True, timeout=60).stdout
цель, ком = [], ""
for строка in вывод.splitlines():
    строка = строка.strip()
    if строка.startswith("CommandLine="):
        ком = строка
    elif строка.startswith("ProcessId=") and "partiya_gen.py" in ком:
        цель.append(строка.split("=", 1)[1])
for пид in цель:
    r = subprocess.run(["taskkill", "/PID", пид, "/F"],
                       capture_output=True, text=True, timeout=60)
    print("  снят %s: rc=%s" % (пид, r.returncode))
if not цель:
    print("  идущих прогонов не было")

if not os.path.exists(СКРИПТ):
    print("НЕТ %s — сначала polozhit_v_ops.py" % СКРИПТ)
    sys.exit(2)
print("\nразмер partiya_gen.py: %d байт, изменён %d с назад"
      % (os.path.getsize(СКРИПТ), int(time.time() - os.path.getmtime(СКРИПТ))))

print("\n=== ПУСКАЮ ЗАНОВО ===")
for арг in ПРОГОНЫ:
    метка = time.strftime("%m%d-%H%M%S")
    основа = os.path.join(КАТАЛОГ, "partiya_gen-%s" % метка)
    лог, ошибки = основа + ".log", основа + ".err"
    список = ", ".join("'" + a.replace("'", "''") + "'"
                       for a in [СКРИПТ] + арг)
    ком = ("$env:PYTHONIOENCODING='utf-8'; "
           "Start-Process -FilePath '%s' -ArgumentList %s "
           "-WindowStyle Hidden -RedirectStandardOutput '%s' "
           "-RedirectStandardError '%s'" % (ПИТОН, список, лог, ошибки))
    subprocess.run(["powershell", "-NoProfile", "-Command", ком], timeout=90)
    print("  пущено: %s" % " ".join(арг))
    print("    лог: %s" % os.path.basename(лог))
    time.sleep(2)

time.sleep(20)
print("\n=== ЧТО ЖИВО ЧЕРЕЗ 20 СЕКУНД ===")
вывод = subprocess.run(
    ["wmic", "process", "where", "name='python.exe'",
     "get", "ProcessId,CommandLine", "/format:list"],
    capture_output=True, text=True, timeout=60).stdout
ком = ""
for строка in вывод.splitlines():
    строка = строка.strip()
    if строка.startswith("CommandLine="):
        ком = строка
    elif строка.startswith("ProcessId=") and "partiya_gen.py" in ком:
        print("  PID %s | %s" % (строка.split("=", 1)[1], ком[12:150]))
