# -*- coding: utf-8 -*-
"""Живы ли фоновые генерации и что они пишут в лог."""
import io
import json
import os
import subprocess
import time


def жив(pid):
    if not pid:
        return False
    в = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid],
                       capture_output=True, text=True).stdout
    return str(pid) in в


def хвост(путь, n=900):
    try:
        т = io.open(путь, encoding="utf-8", errors="replace").read()
        return т[-n:], int(time.time() - os.path.getmtime(путь))
    except Exception as e:  # noqa: BLE001
        return "нет: %s" % e, -1


pid = io.open(r"C:\sender\_ops\gen500.pid").read().strip()
print("ОСНОВНАЯ ПАРТИЯ: pid %s жив=%s" % (pid, жив(pid)))
т, с = хвост(r"C:\sender\_ops\gen500.log")
print("   лог обновлялся %d с назад, хвост:\n%s" % (с, т))
try:
    print("   прогресс: %s" % io.open(r"C:\sender\_ops\gen500-progress.json",
                                    encoding="utf-8").read()[:300])
except Exception:  # noqa: BLE001
    pass
print("")
в = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get",
                    "ProcessId,CommandLine"], capture_output=True, text=True).stdout
print("python-процессы со словом sravnit/generaciya:")
for с_ in в.splitlines():
    if "sravnit" in с_ or "generaciya" in с_:
        print("   " + " ".join(с_.split())[:200])
т, с = хвост(r"C:\sender\_ops\sravnenie.log")
print("СРАВНЕНИЕ: лог обновлялся %d с назад, хвост:\n%s" % (с, т))
print("=== ЖИВЫ ЛИ ГЕНЕРАЦИИ ===")
