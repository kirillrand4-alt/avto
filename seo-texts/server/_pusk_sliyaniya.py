# -*- coding: utf-8 -*-
r"""Пуск слияния собранного в базу отдельным процессом."""
import json
import os
import subprocess
import sys
import time

ЛОГ = r'C:\sender\server\roli_sliyanie.log'
ФЛАГИ = 0x00000008 | 0x00000200
уже = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*roli_telefonov*'} | %{ $_.ProcessId }"],
    capture_output=True, text=True, timeout=90)
живые = [s.strip() for s in (уже.stdout or '').split() if s.strip()]
if живые:
    print(json.dumps({'ещё_идёт_сбор': живые}, ensure_ascii=False))
    raise SystemExit
f = open(ЛОГ, 'a', encoding='utf-8')
f.write('\n=== слияние %s ===\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
f.flush()
p = subprocess.Popen([sys.executable, r'C:\sender\server\roli_telefonov.py',
                      '--sliyanie'], stdout=f, stderr=subprocess.STDOUT,
                     cwd=r'C:\sender\server', creationflags=ФЛАГИ,
                     env=dict(os.environ))
print(json.dumps({'pid': p.pid, 'лог': ЛОГ}, ensure_ascii=False))
