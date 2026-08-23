# -*- coding: utf-8 -*-
r"""Пуск ЭТАПА СБОРА отдельным процессом (в базу не пишет — только в файл)."""
import json
import os
import subprocess
import sys
import time

ЛОГ = r'C:\sender\server\roli_telefonov.log'
ФЛАГИ = 0x00000008 | 0x00000200
уже = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*roli_telefonov*'} | %{ $_.ProcessId }"],
    capture_output=True, text=True, timeout=90)
живые = [s.strip() for s in (уже.stdout or '').split() if s.strip()]
if живые:
    print(json.dumps({'уже_идёт': живые}, ensure_ascii=False))
    raise SystemExit
f = open(ЛОГ, 'a', encoding='utf-8')
f.write('\n=== сбор %s ===\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
f.flush()
p = subprocess.Popen([sys.executable, r'C:\sender\server\roli_telefonov.py',
                      '--primenit'], stdout=f, stderr=subprocess.STDOUT,
                     cwd=r'C:\sender\server', creationflags=ФЛАГИ,
                     env=dict(os.environ))
print(json.dumps({'pid': p.pid}, ensure_ascii=False))
