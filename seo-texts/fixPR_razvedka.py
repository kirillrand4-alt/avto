# -*- coding: utf-8 -*-
r"""fixPR (16.10): что за приложение на панели рассылки (Caddy -> 127.0.0.1:8091) – процесс, папка, есть ли исходники
фронта, как устроены лиды. Только чтение, без секретов в выводе.

    python3 zapusk_na_servere.py fixPR_razvedka.py
"""
import os
import re
import subprocess

o = subprocess.run('netstat -ano -p tcp', shell=True, capture_output=True, text=True, errors='replace').stdout
pid = next((l.split()[-1] for l in o.splitlines() if re.search(r'127\.0\.0\.1:8091\s|0\.0\.0\.0:8091\s', l) and 'LISTEN' in l.upper()), None)
print('порт 8091, PID:', pid)
if pid:
    w = subprocess.run('wmic process where processid=%s get CommandLine,ExecutablePath /format:list' % pid, shell=True,
                       capture_output=True, text=True, errors='replace').stdout
    w = re.sub(r'(?i)(token|key|secret|password)=\S+', r'\1=<скрыто>', w)
    print(w.strip()[:600])
for kand in (r'C:\sender', r'C:\sender\panel', r'C:\sender\server', r'C:\sender\web', r'C:\panel'):
    if os.path.isdir(kand):
        print('\n%s: %s' % (kand, sorted(os.listdir(kand))[:60]))
for kor, papki, fajly in os.walk(r'C:\sender'):
    papki[:] = [p for p in papki if p not in ('node_modules', '.git', '__pycache__', 'venv', '.venv', 'drop-storage', 'checko_meyer')]
    if kor.count(os.sep) > 4:
        continue
    for f in fajly:
        if f in ('package.json', 'vite.config.ts', 'vite.config.js') or re.search(r'lead|lid', f, re.I) and f.endswith(('.py', '.ts', '.tsx', '.js')):
            print('  ', os.path.join(kor, f))
