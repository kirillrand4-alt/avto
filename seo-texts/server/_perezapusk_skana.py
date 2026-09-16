# -*- coding: utf-8 -*-
r"""Погасить зависший скан и поднять заново БЕЗ БУФЕРИЗАЦИИ.

Прошлый запуск (13:34) за 55 минут не написал ни строки: CPU не рос, потоков 2,
сетевых соединений ноль, лог пуст. Пустой лог был следствием буферизации stdout,
поэтому место остановки не видно. Теперь python -u: любая печать попадает в лог
сразу, и станет ясно, встаёт он на чтении stdin, на импортах или на базе.
"""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
o = {}

# 1. Гасим старое дерево: и python news_scan.py, и его cmd-обёртку.
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process | Where-Object {"
     "($_.Name -like 'python*' -or $_.Name -eq 'cmd.exe') -and "
     "$_.CommandLine -like '*news_scan*'} | "
     '%{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }'],
    capture_output=True, text=True, timeout=120)
o['погашено'] = [s.strip() for s in (out.stdout or '').split() if s.strip()]
time.sleep(3)

# 2. Поднимаем заново.
МЕТКА = time.strftime('%d%m-%H%M')
ARGS = os.path.join(DIR, 'news_args_%s.json' % МЕТКА)
LOG = os.path.join(DIR, 'news_scan_%s.log' % МЕТКА)
args = {
    'collectors': ['vk', 'regional', 'frp', 'zakupki', 'google'],   # browser убран: он мог и вешать
    'days': 45,
    'max_items': 6,
    'enrich': True,
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
cmd = '""%s" -u news_scan.py < "%s" > "%s" 2>&1"' % (python, ARGS, LOG)
DETACHED = 0x00000008 | 0x00000200
p = subprocess.Popen('cmd /c ' + cmd, cwd=DIR, shell=False, creationflags=DETACHED,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
o['обёртка_pid'] = p.pid

# 3. Смотрим первые полторы минуты: пошла ли печать.
for сек in (20, 50, 90):
    time.sleep(сек - (o.get('_ждали') or 0))
    o['_ждали'] = сек
    o['лог_на_%dс' % сек] = os.path.getsize(LOG) if os.path.exists(LOG) else 'нет файла'
o.pop('_ждали', None)
if os.path.exists(LOG):
    with open(LOG, encoding='utf-8', errors='replace') as f:
        o['лог'] = f.read()[-1500:]
o['файл_лога'] = LOG
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
