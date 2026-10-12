# -*- coding: utf-8 -*-
# 12.10: шлюз провайдера лежит по Luna (503 «upstream»/«нет провайдеров») — пересборка паспортов копила отказы.
# Остановить её; раз в 5 мин пробовать gpt-5.6-luna; 3 удачи подряд — снова запустить _pereborka_pasportov.py (резюм по
# meyer7-pereborka-pasportov-sdelano.txt). Лог: storozh_pasportov_*.log.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender'); os.chdir(DIR)
if '--vnutri' not in sys.argv:
    r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine'], capture_output=True,
                       text=True, errors='replace')
    убиты = []
    for x in r.stdout.splitlines():
        if '_pereborka_pasportov.py' in x or '_storozh_pasportov.py' in x and '--vnutri' in x:
            pid = x.strip().split()[-1]
            if pid.isdigit():
                subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
                убиты.append(pid)
    лог = os.path.join(DIR, 'storozh_pasportov_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    print('===ИТОГ===', json.dumps({'остановлены': убиты, 'сторож': p.pid, 'лог': os.path.basename(лог)}, ensure_ascii=False))
    sys.exit(0)
import gen_provider as GP  # noqa: E402
к = GP.make_client()
подряд = 0
while подряд < 3:
    try:
        GP.call(к, [{'role': 'user', 'content': 'Перечисли через запятую пять фруктов.'}], model='gpt-5.6-luna', attempts=1)
        подряд += 1
        print(time.strftime('%H:%M:%S'), 'luna отвечает', подряд, flush=True)
        time.sleep(30)
    except Exception as e:  # noqa: BLE001
        подряд = 0
        print(time.strftime('%H:%M:%S'), 'luna недоступна:', str(e)[60:140], flush=True)
        time.sleep(300)
print(time.strftime('%H:%M:%S'), 'шлюз ожил — запускаю пересборку паспортов', flush=True)
r = subprocess.run([sys.executable, os.path.join(DIR, '_pereborka_pasportov.py')], cwd=DIR, capture_output=True, text=True,
                   errors='replace')
print((r.stdout + r.stderr)[-500:], flush=True)
