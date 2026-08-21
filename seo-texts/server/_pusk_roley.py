# -*- coding: utf-8 -*-
r"""Пуск записи ролей отдельным процессом: переживёт таймаут раннера и рестарт."""
import json
import os
import subprocess
import sys

ЛОГ = r'C:\sender\server\roli_telefonov.log'
ФЛАГИ = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
уже = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*roli_telefonov*'} | "
     '%{ $_.ProcessId }'], capture_output=True, text=True, timeout=90)
живые = [s.strip() for s in (уже.stdout or '').split() if s.strip()]
if живые:
    print(json.dumps({'уже_идёт': живые}, ensure_ascii=False))
    raise SystemExit
f = open(ЛОГ, 'a', encoding='utf-8')
f.write('\n=== пуск %s ===\n' % __import__('time').strftime('%Y-%m-%d %H:%M:%S'))
f.flush()
p = subprocess.Popen([sys.executable, r'C:\sender\server\roli_telefonov.py',
                      '--primenit'], stdout=f, stderr=subprocess.STDOUT,
                     cwd=r'C:\sender\server', creationflags=ФЛАГИ,
                     env=dict(os.environ))
print(json.dumps({'pid': p.pid, 'лог': ЛОГ}, ensure_ascii=False))
