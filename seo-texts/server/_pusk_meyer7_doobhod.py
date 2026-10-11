# -*- coding: utf-8 -*-
# 11.10 17:55: дообход пропущенных страниц контактов (kc_doobhod) — отдельным процессом, стоп при шагах после агентов.
# отдельным процессом; файл обхода сейчас никто не пишет (агенты пишут свой журнал), стоп — при шагах после агентов.
import json, os, subprocess, sys, time, hashlib
DIR = r'C:\sender\server'
ЛОГ = os.path.join(DIR, 'konveyer_meyer7_doobhod_%s.log' % time.strftime('%d%m-%H%M'))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_doobhod.py'), '--metka=doobhod_meyer7'], cwd=DIR,
                     creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, KC_NABOR='meyer7', KC_CEL='meyer', PYTHONIOENCODING='utf-8'))
выход.close()
time.sleep(45)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ),
     'sha': {ф: hashlib.sha256(open(os.path.join(DIR, ф), 'rb').read()).hexdigest()[:16] for ф in ('kc_doobhod.py',)}}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    o['хвост'] = open(ЛОГ, encoding='utf-8', errors='replace').read()[-400:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
