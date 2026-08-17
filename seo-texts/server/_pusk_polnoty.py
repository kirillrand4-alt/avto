# -*- coding: utf-8 -*-
"""Запустить замер полноты по сайтам отдельным процессом — переживёт таймаут."""
import json
import os
import subprocess
import sys
import time

D = r'C:\sender\server'
свой = str(os.getpid())
p = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine'],
                   capture_output=True, text=True)
идёт = [l for l in p.stdout.splitlines()
        if 'polnota_sayta.py' in l and l.split()[-1] != свой]
out = {'уже_идёт': bool(идёт)}
вых = os.path.join(D, 'polnota_sayta.out')
if not идёт:
    f = open(вых, 'wb')
    pr = subprocess.Popen([sys.executable, os.path.join(D, 'polnota_sayta.py')],
                          cwd=D, stdout=f, stderr=subprocess.STDOUT,
                          creationflags=0x00000008 | 0x00000200)
    out['pid'] = pr.pid
    time.sleep(5)
out['размер_вывода'] = os.path.getsize(вых) if os.path.exists(вых) else 0
if out['размер_вывода']:
    out['хвост'] = open(вых, encoding='utf-8', errors='replace').read()[-1500:]
print(json.dumps(out, ensure_ascii=False)[:2500])
