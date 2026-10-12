# -*- coding: utf-8 -*-
"""Остановить текущий прогон «Россия 9000» (partiya_gen)."""
import io
import subprocess
pid = io.open(r"C:\sender\_ops\gen-rossiya-9000.pid").read().strip()
subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
print("прогон %s остановлен" % pid)
print("=== 9000 СНЯТ ===")
