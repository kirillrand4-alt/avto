# -*- coding: utf-8 -*-
import json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
ЛОГ = os.path.join(DIR, 'kc_raspakovka_%s.log' % time.strftime('%d%m-%H%M'))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
o = {'свободно_C_ГБ': round(shutil.disk_usage('C:\\').free / 1e9, 1)}
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_raspakovka.py'), 'kc-proekty-0610-1436.tar'],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False)
выход.close()
time.sleep(60)
o.update({'pid': p.pid, 'лог': os.path.basename(ЛОГ)})
if os.path.getsize(ЛОГ):
    o['хвост'] = open(ЛОГ, encoding='utf-8', errors='replace').read()[-500:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
