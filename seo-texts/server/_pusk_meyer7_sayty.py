# -*- coding: utf-8 -*-
# Полный прогон Meyer: сайты по названию (pilot_sayty_dobor) отдельным процессом с меткой шага волн — оркестратор видит
# его как идущий и второй не запускает (09.10: перезапуск после правки потоков 8 -> 3 из-за xmlriver HTTP 429).
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7'
ЛОГ = os.path.join(DIR, 'konveyer_%s_pilot_sayty_dobor_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'pilot_sayty_dobor.py'), '--nabor=' + НАБОР, '--shag=pilot_sayty_dobor.py'],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT,
                     close_fds=False, env=dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1',
                                               PILOT_SNIMKI='1', PILOT_SAYTY_MAX='24000', PILOT_SAYTY_POTOKOV='3'))
выход.close()
time.sleep(20)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    o['хвост'] = open(ЛОГ, encoding='utf-8', errors='replace').read()[-400:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
