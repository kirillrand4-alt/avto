# -*- coding: utf-8 -*-
# 11.10 19:45: kc_skrytye в один процесс — 8 мин на 1000 компаний (16 тыс. ≈ 2 ч, не успевает до шагов после агентов):
# останавливаем его и запускаем N процессов по долям ИНН, каждый пишет свой файл; слияние — KC_SKRYTYE_REZHIM=slit.
import json, os, subprocess, sys, time, hashlib
N = 4
DIR = r'C:\sender\server'
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
стоп = subprocess.run(['powershell', '-NoProfile', '-Command',
    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like '*kc_skrytye.py*' } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"], capture_output=True, text=True).stdout.split()
time.sleep(3)
o = {'остановлено': стоп, 'доли': []}
for k in range(N):
    лог = os.path.join(DIR, 'konveyer_meyer7_skrytye_d%d_%s.log' % (k, time.strftime('%d%m-%H%M')))
    выход = open(лог, 'wb')
    p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_skrytye.py'), '--metka=skrytye_meyer7_d%d' % k], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT,
                         close_fds=False, env=dict(os.environ, KC_NABOR='meyer7', KC_CEL='meyer', KC_SKRYTYE_PROBA='0',
                                                   KC_SKRYTYE_DOLYA='%d/%d' % (k, N), KC_SKRYTYE_POTOKOV='2',
                                                   PYTHONIOENCODING='utf-8'))
    выход.close()
    o['доли'].append({'pid': p.pid, 'лог': os.path.basename(лог)})
time.sleep(40)
for д in o['доли']:
    п = os.path.join(DIR, д['лог'])
    д['хвост'] = open(п, encoding='utf-8', errors='replace').read()[-200:] if os.path.exists(п) else ''
o['sha'] = hashlib.sha256(open(os.path.join(DIR, 'kc_skrytye.py'), 'rb').read()).hexdigest()[:16]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
