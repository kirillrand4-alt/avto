# -*- coding: utf-8 -*-
"""Жив ли прогон 9000: pid, процесс, свежесть лога и журнала."""
import io
import os
import subprocess
import time
pid = io.open(r"C:\sender\_ops\gen-rossiya-9000.pid").read().strip()
out = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid], capture_output=True, text=True).stdout
print("pid %s жив: %s" % (pid, pid in out))
for п in (r"C:\sender\_ops\gen-rossiya-9000.log", r"C:\sender\_ops\gen-rossiya-9000.jsonl"):
    print("%s: обновлён %d с назад" % (os.path.basename(п), time.time() - os.path.getmtime(п)))
print("=== ЖИВ ЛИ 9000 ===")
