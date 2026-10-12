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
# 12.10, владелец: «запусти всё, может ночью оживёт» — шлюз мигает, «3 ответа подряд» может не случиться никогда.
# Теперь: пересборка сразу; отказы шлюза (отложенные) — повтор кругами через 20 мин, до 15 кругов; потолок $145 — в самой
# пересборке (накопленная сумма, meyer7-pereborka-stoimost.json).
for круг in range(1, 16):
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(DIR, '_pereborka_pasportov.py'), '--vnutri'], cwd=DIR, capture_output=True,
                       text=True, errors='replace')
    хв = (r.stdout + r.stderr)
    итог = [s for s in хв.splitlines() if 'ИТОГ ПЕРЕСБОРКИ' in s or 'ПОТОЛОК' in s or s.startswith('к пересборке')]
    print(time.strftime('%H:%M:%S'), 'круг', круг, 'за %.0f мин' % ((time.time() - t0) / 60), '|', ' | '.join(итог)[-700:], flush=True)
    if any('ПОТОЛОК' in s for s in итог) or any('бедных 0 средних 0' in s for s in итог):
        break
    time.sleep(1200)
print(time.strftime('%H:%M:%S'), 'СТОРОЖ ПАСПОРТОВ ГОТОВ', flush=True)
