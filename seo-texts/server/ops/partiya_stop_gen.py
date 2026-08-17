# -*- coding: utf-8 -*-
"""Остановить генерацию партии на сервере по команде владельца.

Серверный процесс переживает смерть локального драйвера: убивать надо здесь,
по имени файла в командной строке. Старый partiya_ubit_dubli.py искал строку
«_gen_partiya», которой в нынешнем имени нет, и не находил ничего - поэтому
отдельный оп с правильным именем.

Терять нечего: текст письма ложится в журнал ДО очереди, а недописанные
письма добьёт следующий круг (резюм по ИНН).
"""
import subprocess

ИМЯ = "partiya_gen.py"

out = subprocess.run(["wmic", "process", "where", "name='python.exe'",
                      "get", "ProcessId,CommandLine"],
                     capture_output=True, text=True, timeout=40).stdout
пиды = []
for l in out.splitlines():
    if ИМЯ not in l:
        continue
    ч = l.split()
    if ч and ч[-1].isdigit():
        пиды.append(int(ч[-1]))
        print("нашёл:", l.strip()[:150])

for pid in пиды:
    r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, text=True, timeout=30)
    print(f"  убит {pid}: rc={r.returncode} {r.stdout.strip()[:70]}")
print("остановлено прогонов:", len(пиды))
