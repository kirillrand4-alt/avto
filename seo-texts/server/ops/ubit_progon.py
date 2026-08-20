# -*- coding: utf-8 -*-
"""Снять идущие прогоны partiya_gen.py (по требованию оператора)."""
import subprocess

вывод = subprocess.run(
    ["wmic", "process", "where",
     "name='python.exe'", "get", "ProcessId,CommandLine", "/format:list"],
    capture_output=True, text=True, timeout=60).stdout
цель, ком = [], ""
for строка in вывод.splitlines():
    строка = строка.strip()
    if строка.startswith("CommandLine="):
        ком = строка
    elif строка.startswith("ProcessId=") and "partiya_gen.py" in ком:
        цель.append(строка.split("=", 1)[1])
if not цель:
    print("идущих партий нет")
else:
    for пид in цель:
        r = subprocess.run(["taskkill", "/PID", пид, "/F"],
                           capture_output=True, text=True, timeout=60)
        print(f"снят {пид}: rc={r.returncode} {r.stdout.strip()[:80]}")
