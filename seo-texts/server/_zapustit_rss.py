# -*- coding: utf-8 -*-
r"""Поднять цепочку по RSS-донорам отдельным процессом (переживает раннер)."""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
ЦЕПЬ = os.path.join(DIR, '_pusk_rss_cepochka.py')
ЛОГ = os.path.join(DIR, 'rss_cepochka_%s.log' % time.strftime('%d%m-%H%M'))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python):
    python = sys.executable
DETACHED = 0x00000008 | 0x00000200
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', ЦЕПЬ], cwd=DIR, creationflags=DETACHED,
                     stdin=subprocess.DEVNULL, stdout=выход,
                     stderr=subprocess.STDOUT, close_fds=False)
выход.close()
time.sleep(50)
жив = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$pr = Get-Process -Id %d -ErrorAction SilentlyContinue; "
     "if ($pr) { [math]::Round($pr.CPU,2) } else { 'нет процесса' }" % p.pid],
    capture_output=True, text=True, timeout=90)
o = {'pid': p.pid, 'cpu_через_50с': (жив.stdout or '').strip(), 'лог': ЛОГ}
for имя in sorted(os.listdir(DIR)):
    if имя.startswith('rss_') and имя.endswith('.log'):
        o.setdefault('логи', []).append((имя, os.path.getsize(os.path.join(DIR, имя))))
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
