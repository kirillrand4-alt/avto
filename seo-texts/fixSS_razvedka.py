# -*- coding: utf-8 -*-
r"""fixSS (19.10): где задан CENTRO_SESSION_SECRET для панели Meyer (после перезагрузки: «не настроен или слишком
короткий»). Только чтение; значения НЕ печатаются – только наличие и длина.

    python3 zapusk_na_servere.py fixSS_razvedka.py
"""
import io
import os
import re
import subprocess

IMYA = 'CENTRO_SESSION_SECRET'
print('окружение запускающего процесса: %s' % (('есть, длина %d' % len(os.environ[IMYA])) if os.environ.get(IMYA) else 'нет'))
print('пользователь процесса:', os.environ.get('USERNAME'), os.environ.get('USERDOMAIN'))
for f in (r'C:\centro2\.env', r'C:\seostat\.env', r'C:\centro\.env', r'C:\sender\.env'):
    if os.path.exists(f):
        t = io.open(f, encoding='utf-8', errors='replace').read()
        m = re.search(r'^\s*%s\s*=\s*(.*)$' % IMYA, t, re.M)
        print('%s: %s' % (f, ('есть, длина %d' % len(m.group(1).strip().strip('"\''))) if m else 'ключа нет'))
for kl in (r'HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment', r'HKCU\Environment'):
    o = subprocess.run('reg query "%s" /v %s' % (kl, IMYA), shell=True, capture_output=True, text=True, errors='replace').stdout
    m = re.search(r'%s\s+REG_\w+\s+(\S+)' % IMYA, o)
    print('%s: %s' % (kl, ('есть, длина %d' % len(m.group(1))) if m else 'нет'))
t = io.open(r'C:\centro2\zapusk.py', encoding='utf-8', errors='replace').read()
print('\nzapusk.py про .env/секрет:', [s.strip()[:150] for s in t.splitlines() if re.search(r'\.env|SECRET|environ', s)][:12])
for f in (r'C:\centro2\app\api\routes_centro_sales.py', r'C:\centro2\app\obzvon.py'):
    for i, s in enumerate(io.open(f, encoding='utf-8').read().splitlines(), 1):
        if IMYA in s:
            print('%s:%d: %s' % (os.path.basename(f), i, s.strip()[:170]))
o = subprocess.run('schtasks /query /tn "\\centro2-meyer" /v /fo list', shell=True, capture_output=True, text=True, errors='replace').stdout
print('\nзадача автозапуска:', [s.strip() for s in o.splitlines() if re.search(r'(?i)run as|запуск от|task to run|задача для|status|состояние|last run|прошлый|start in|рабоч', s)][:10])
o = subprocess.run('netstat -ano -p tcp', shell=True, capture_output=True, text=True).stdout
pid = next((l.split()[-1] for l in o.splitlines() if ':8016 ' in l and 'LISTEN' in l.upper()), None)
print('порт 8016 PID:', pid)
if pid:
    w = subprocess.run('wmic process where processid=%s get CommandLine /format:list' % pid, shell=True, capture_output=True, text=True, errors='replace').stdout
    print(w.strip()[:300])
