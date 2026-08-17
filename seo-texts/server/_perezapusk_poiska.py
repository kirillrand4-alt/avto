# -*- coding: utf-8 -*-
"""Перезапустить поиск сайтов и убедиться, что он ЖИВ, а не падает."""
import json
import os
import subprocess
import sys
import time

D = r'C:\sender\server'
out = {}
p = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine'],
                   capture_output=True, text=True)
for l in [x for x in p.stdout.splitlines() if 'poisk_saytov' in x]:
    subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, text=True)
time.sleep(2)
лог = r'C:\sender\poisk_saytov.out'
было = os.path.getsize(лог) if os.path.exists(лог) else 0
f = open(лог, 'ab')
pr = subprocess.Popen([sys.executable, os.path.join(D, 'poisk_saytov.py'), '--vse', '500', '8'],
                      cwd=D, stdout=f, stderr=subprocess.STDOUT,
                      creationflags=0x00000008 | 0x00000200)
out['pid'] = pr.pid
time.sleep(45)                      # даём время упасть, если падает
q = subprocess.run(['wmic', 'process', 'where', "ProcessId=%d" % pr.pid, 'get', 'ProcessId'],
                   capture_output=True, text=True)
out['жив_через_45_секунд'] = str(pr.pid) in q.stdout
out['хвост_лога'] = open(лог, encoding='utf-8', errors='replace').read()[было:][-500:]
print(json.dumps(out, ensure_ascii=False, indent=1))
