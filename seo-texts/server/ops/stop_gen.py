# -*- coding: utf-8 -*-
"""Остановить генерацию по pid-файлу: stop_gen.py gen-kc-9000"""
import io, subprocess, sys
pid = io.open(r"C:\sender\_ops\%s.pid" % sys.argv[1]).read().strip()
print(subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True, text=True, errors="replace").stdout)
