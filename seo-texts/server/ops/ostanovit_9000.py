# -*- coding: utf-8 -*-
"""Остановить текущий прогон 9000 по pid-файлу (с деревом процессов)."""
import io
import subprocess
pid = io.open(r"C:\sender\_ops\gen-rossiya-9000.pid", encoding="utf-8").read().strip()
р = subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True, text=True)
print("pid %s: %s" % (pid, (р.stdout or р.stderr).strip()[:200]))
print("=== СТОП 9000 ===")
