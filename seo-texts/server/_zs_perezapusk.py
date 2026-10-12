# -*- coding: utf-8 -*-
# 12.10: серверный обход по логике кубика — перезапуск с ZS_POTOKOV (темп упал до ~2500 сайтов/ч на 48 потоках).
# Журнал meyer7-server-obhod.jsonl — резюм (сделанное пропускается); --zabrat НЕ повторяется (иначе строки, уже
# возвращённые Зенке как «защита», ушли бы из её очереди обратно на сервер и потерялись).
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
ПОТОКОВ = '96'
r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine'], capture_output=True,
                   text=True, errors='replace')
убиты = []
for x in r.stdout.splitlines():
    if 'zenka_server_obhod.py' in x and '_pusk' not in x and 'perezapusk' not in x:
        pid = x.strip().split()[-1]
        if pid.isdigit():
            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
            убиты.append(pid)
time.sleep(5)
лог = os.path.join(DIR, 'konveyer_meyer7_server_obhod_%s.log' % time.strftime('%d%m-%H%M'))
with open(лог, 'wb') as в:
    p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'zenka_server_obhod.py')], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8', ZS_POTOKOV=ПОТОКОВ))
time.sleep(30)
print('===ИТОГ===')
print(json.dumps({'остановлены': убиты, 'pid': p.pid, 'лог': os.path.basename(лог),
                  'хвост': open(лог, encoding='utf-8', errors='replace').read()[-300:]}, ensure_ascii=False))
