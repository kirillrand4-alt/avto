# -*- coding: utf-8 -*-
# 12.10, владелец: «делай, со всем согласен». 1) из очереди Зенки — строки, чей сайт у сервера раньше открывался
# (zenka_server_obhod.py --zabrat), 2) серверный обход по логике кубика — отвязанным процессом (48 потоков).
# Лог: konveyer_meyer7_server_obhod_*.log.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
os.chdir(DIR)
r = subprocess.run([sys.executable, '-u', os.path.join(DIR, 'zenka_server_obhod.py'), '--zabrat'], cwd=DIR,
                   capture_output=True, text=True, errors='replace', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
лог = os.path.join(DIR, 'konveyer_meyer7_server_obhod_%s.log' % time.strftime('%d%m-%H%M'))
with open(лог, 'wb') as в:
    p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'zenka_server_obhod.py')], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8', ZS_POTOKOV='48'))
time.sleep(60)
print('===ИТОГ===')
print(json.dumps({'забор': (r.stdout + r.stderr)[-600:], 'pid': p.pid, 'лог': os.path.basename(лог),
                  'хвост': open(лог, encoding='utf-8', errors='replace').read()[-500:]}, ensure_ascii=False, indent=1))
