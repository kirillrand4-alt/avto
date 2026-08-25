# -*- coding: utf-8 -*-
"""Остановить процесс добора (только его, по имени скрипта)."""
import subprocess
import time

out = subprocess.run(['wmic', 'process', 'where', "name='python.exe'",
                      'get', 'ProcessId,CommandLine'], capture_output=True,
                     text=True, timeout=60).stdout
ubito = []
for s in out.splitlines():
    if '_dobor_1_rabota.py' in s:
        pid = s.strip().split()[-1]
        if pid.isdigit():
            r = subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True,
                               text=True, timeout=30)
            ubito.append((pid, r.stdout.strip()[:60] or r.stderr.strip()[:60]))
print('остановлено:', ubito or 'процесс не найден')
time.sleep(2)
out2 = subprocess.run(['wmic', 'process', 'where', "name='python.exe'",
                       'get', 'ProcessId,CommandLine'], capture_output=True,
                      text=True, timeout=60).stdout
print('осталось процессов добора:',
      sum(1 for s in out2.splitlines() if '_dobor_1_rabota.py' in s))
