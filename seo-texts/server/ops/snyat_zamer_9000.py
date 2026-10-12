# -*- coding: utf-8 -*-
"""Снять замерочный прогон partiya_gen («Россия 9000»), пока он на дешёвой
стадии (гейт/предклассификатор, писем ещё нет): сравнению моделей нужен
шлюз без лишней нагрузки — владелец 12.10: «сначала сравнение»."""
import io
import subprocess

pid = io.open(r"C:\sender\_ops\gen-rossiya-9000.pid").read().strip()
в = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid], capture_output=True,
                   text=True).stdout
if pid in в:
    subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
    print("снят замерочный прогон, pid %s" % pid)
else:
    print("процесс %s уже не жив" % pid)
print("=== ЗАМЕР СНЯТ ===")
