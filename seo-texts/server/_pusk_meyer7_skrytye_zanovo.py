# -*- coding: utf-8 -*-
# 11.10 19:50: перезапуск kc_skrytye после проверки (156 из 209 «новых» почт — адреса в <!-- -->, обход их исключил):
# стоп долей -> файлы долей в .brak (отметки «без находок» остаются) -> очистка записей первого прогона -> 4 доли заново.
# Всё — в отдельном процессе (--vnutri), лог konveyer_meyer7_skrytye_zanovo_*.log.
import glob, json, os, subprocess, sys, time
DIR = r'C:\sender\server'
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'konveyer_meyer7_skrytye_zanovo_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([python, '-u', os.path.abspath(__file__), '--vnutri', '--metka=skrytye_zanovo_meyer7'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                             close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    time.sleep(60)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                     ensure_ascii=False, indent=1))
    sys.exit(0)
стоп = subprocess.run(['powershell', '-NoProfile', '-Command',
    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like '*kc_skrytye.py*' } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"], capture_output=True, text=True).stdout.split()
print('остановлено', стоп, flush=True)
time.sleep(3)
for ф in glob.glob(os.path.join(DIR, 'meyer7-skrytye-dolya-*.jsonl')):
    os.replace(ф, ф + '.brak')
    print('в брак', os.path.basename(ф), flush=True)
env0 = dict(os.environ, KC_NABOR='meyer7', KC_CEL='meyer', PYTHONIOENCODING='utf-8')
r = subprocess.run([python, '-u', os.path.join(DIR, 'kc_skrytye.py'), '--metka=skrytye_ochistka_meyer7'], cwd=DIR,
                   env=dict(env0, KC_SKRYTYE_REZHIM='ochistka'), capture_output=True, text=True, errors='replace')
print('очистка код', r.returncode, (r.stdout + r.stderr)[-400:], flush=True)
if r.returncode != 0:
    sys.exit(1)
N = 4
for k in range(N):
    лог = os.path.join(DIR, 'konveyer_meyer7_skrytye_d%d_%s.log' % (k, time.strftime('%d%m-%H%M')))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_skrytye.py'), '--metka=skrytye_meyer7_d%d' % k], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                             close_fds=False, env=dict(env0, KC_SKRYTYE_PROBA='0', KC_SKRYTYE_DOLYA='%d/%d' % (k, N),
                                                       KC_SKRYTYE_POTOKOV='2'))
    print('доля', k, 'pid', p.pid, os.path.basename(лог), flush=True)
print('ГОТОВО', flush=True)
