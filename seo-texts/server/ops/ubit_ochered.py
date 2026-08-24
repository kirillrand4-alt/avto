# -*- coding: utf-8 -*-
"""Снять драйвер очереди И его текущий блок.

Порядок важен: сперва драйвер, иначе он увидит смерть блока как обычное
завершение и запустит следующий с тем же неверным порогом.
"""
import subprocess

вывод = subprocess.run(
    ["wmic", "process", "where", "name='python.exe'", "get",
     "ProcessId,CommandLine", "/format:list"],
    capture_output=True, text=True, timeout=60).stdout
пары, ком = [], ""
for строка in вывод.splitlines():
    строка = строка.strip()
    if строка.startswith("CommandLine="):
        ком = строка
    elif строка.startswith("ProcessId=") and строка.split("=", 1)[1].strip():
        пары.append((строка.split("=", 1)[1].strip(), ком))

for метка in ("ochered_vladeltsa.py", "partiya_gen.py"):
    цели = [п for п, к in пары if метка in к]
    if not цели:
        print("%s: процессов нет" % метка)
        continue
    for пид in цели:
        r = subprocess.run(["taskkill", "/PID", пид, "/F"],
                           capture_output=True, text=True, timeout=60)
        print("%s pid=%s -> %s" % (метка, пид,
                                   (r.stdout or r.stderr).strip()[:90]))
