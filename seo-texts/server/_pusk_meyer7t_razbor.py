# -*- coding: utf-8 -*-
# Проба Meyer: разбор выдачи набора meyer7t отдельным процессом (резюм: сделанное пропускается) с POISK_RAZBOR_POTOKOV.
# 09.10: в шаге 0 конвейера страницы каталогов шли 42/мин при 40 потоках (таймауты и 429 у каталогов) — дочистка в 120.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7t'
ЛОГ = os.path.join(DIR, 'konveyer_%s_poisk_razbor_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'poisk_razbor.py')],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, POISK_NABOR=НАБОР, KC_NABOR=НАБОР, POISK_RAZBOR_POTOKOV='120'))
выход.close()
time.sleep(30)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['хвост'] = f.read()[-600:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
