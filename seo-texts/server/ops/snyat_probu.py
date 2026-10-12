# -*- coding: utf-8 -*-
"""Остановить SMTP-пробу партий (резюмируемая: вердикты уже в базах)."""
import io
import subprocess
pid = io.open(r"C:\sender\_ops\smtp-proba-partiy.pid").read().strip()
subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
print("проба %s остановлена" % pid)
print("=== ПРОБА СНЯТА ===")
