# -*- coding: utf-8 -*-
"""Остановить процесс по pid: ubit_pid.py <pid>"""
import subprocess
import sys
print(subprocess.run(["taskkill", "/PID", sys.argv[1], "/F", "/T"], capture_output=True, text=True, errors="replace").stdout)
