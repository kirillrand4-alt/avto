# -*- coding: utf-8 -*-
"""Поднять перекачку текстов отдельным процессом."""
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
ЛОГ = os.path.join(DIR, 'dobor_teksta_%s.log' % time.strftime('%d%m-%H%M'))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python):
    python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'dobor_teksta.py'), '400'],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False)
выход.close()
time.sleep(75)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
отч = os.path.join(DIR, 'dobor_teksta.jsonl')
o['разобрано_строк'] = sum(1 for _ in open(отч, encoding='utf-8', errors='replace')) if os.path.exists(отч) else 0
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['лог_хвост'] = f.read()[-500:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
