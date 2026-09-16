# -*- coding: utf-8 -*-
r"""Запустить добор событий отдельным процессом: он ждёт, пока освободится база."""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
ЛОГ = os.path.join(DIR, 'dobor_signalov_%s.log' % time.strftime('%d%m-%H%M'))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python):
    python = sys.executable
DETACHED = 0x00000008 | 0x00000200
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'dobor_signalov_iz_potoka.py')],
                     cwd=DIR, creationflags=DETACHED, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False)
выход.close()
time.sleep(60)
o = {'pid': p.pid, 'лог': ЛОГ,
     'байт': os.path.getsize(ЛОГ) if os.path.exists(ЛОГ) else None}
if os.path.exists(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['хвост'] = f.read()[-800:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
