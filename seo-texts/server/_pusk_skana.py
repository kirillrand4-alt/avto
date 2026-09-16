# -*- coding: utf-8 -*-
r"""Запуск новостного скана отдельным процессом, переживающим таймаут раннера.

news_scan.py читает аргументы из stdin, поэтому запускаем через cmd с
перенаправлением: «python news_scan.py < args.json > log 2>&1».
DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP — чтобы процесс не умер вместе с
раннером (урок: сырой & и дочерние процессы раннера гибнут при его таймауте).
"""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
МЕТКА = time.strftime('%d%m-%H%M')
ARGS = os.path.join(DIR, 'news_args_%s.json' % МЕТКА)
LOG = os.path.join(DIR, 'news_scan_%s.log' % МЕТКА)

# Коллекторы: hh исключён решением владельца 16.09; xmlriver исключён потому,
# что платный (баланс 299 ₽), трата владельцем не разрешена.
args = {
    'collectors': ['vk', 'browser', 'regional', 'frp', 'zakupki', 'google'],
    'days': 45,                 # прошлый прогон закончился 05.08, сегодня 16.09
    'max_items': 6,
    'enrich': True,             # контакты по ВСЕМ новостным лидам — директива владельца
    'enrich_max': 0,
    'icp_only': False,
    'write_db': True,
    'provider_workers': 12,
}
with open(ARGS, 'w', encoding='utf-8') as f:
    json.dump(args, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())

python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python):
    python = sys.executable
cmd = '""%s" news_scan.py < "%s" > "%s" 2>&1"' % (python, ARGS, LOG)
DETACHED = 0x00000008 | 0x00000200
p = subprocess.Popen('cmd /c ' + cmd, cwd=DIR, shell=False, creationflags=DETACHED,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
time.sleep(45)

живые = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'} | "
     'Select-Object ProcessId | ConvertTo-Json -Compress'],
    capture_output=True, text=True, timeout=90)

итог = {'аргументы': args, 'лог': LOG, 'pid_обёртки': p.pid,
        'процессы_news_scan': (живые.stdout or '').strip()[:300]}
if os.path.exists(LOG):
    with open(LOG, encoding='utf-8', errors='replace') as f:
        хвост = f.read()[-1200:]
    итог['лог_первые_45с'] = хвост
else:
    итог['лог_первые_45с'] = 'файла лога ещё нет'
print('===ИТОГ===')
print(json.dumps(итог, ensure_ascii=False, indent=1))
