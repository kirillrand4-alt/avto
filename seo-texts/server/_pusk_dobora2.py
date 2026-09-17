# -*- coding: utf-8 -*-
"""Донести накопленные события из потока в базу (ждёт, если база занята)."""
import json, os, subprocess, sys, time

DIR = r'C:\sender\server'
ЛОГ = os.path.join(DIR, 'dobor_%s.log' % time.strftime('%d%m-%H%M'))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python):
    python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'dobor_signalov_iz_potoka.py')],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False)
выход.close()
time.sleep(75)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['содержимое'] = f.read()[-900:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
