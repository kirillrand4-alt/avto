# -*- coding: utf-8 -*-
r"""Запуск скана БЕЗ cmd: python напрямую, файлы отданы дескрипторами.

Почему переписано. Первые два запуска шли через `cmd /c "python news_scan.py <
args > log"` с DETACHED_PROCESS — и оба раза процесс вставал намертво: CPU не
рос (0.22 за 40 с без изменений), потоков 2, сетевых соединений ноль, лог пуст
даже с python -u. news_scan.py читает аргументы из stdin (`json.load(sys.stdin)`),
а отсоединённому от консоли cmd перенаправление `< файл` не досталось — процесс
честно ждал ввода, которого не будет. Полтора часа скан «работал», не сделав
ничего: ровно тот случай, когда молчание выглядит как работа.

Теперь cmd из цепочки убран: Popen получает открытые файлы напрямую в stdin и
stdout, перенаправлять нечего и некому потеряться.
"""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
o = {}

out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process | Where-Object {"
     "($_.Name -like 'python*' -or $_.Name -eq 'cmd.exe') -and "
     "$_.CommandLine -like '*news_scan*'} | "
     '%{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }'],
    capture_output=True, text=True, timeout=120)
o['погашено_старое'] = [s.strip() for s in (out.stdout or '').split() if s.strip()]
time.sleep(3)

МЕТКА = time.strftime('%d%m-%H%M')
ARGS = os.path.join(DIR, 'news_args_%s.json' % МЕТКА)
LOG = os.path.join(DIR, 'news_scan_%s.log' % МЕТКА)
args = {
    'collectors': ['vk', 'regional', 'frp', 'zakupki', 'google'],
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
DETACHED = 0x00000008 | 0x00000200
вход = open(ARGS, 'rb')
выход = open(LOG, 'wb')
p = subprocess.Popen([python, '-u', 'news_scan.py'], cwd=DIR, creationflags=DETACHED,
                     stdin=вход, stdout=выход, stderr=subprocess.STDOUT,
                     close_fds=False)
o['pid'] = p.pid
вход.close()
выход.close()

for пауза in (25, 35, 40):
    time.sleep(пауза)
    o.setdefault('ход', []).append({
        'через_сек': пауза,
        'лог_байт': os.path.getsize(LOG) if os.path.exists(LOG) else None,
    })
проба = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$pr = Get-Process -Id %d -ErrorAction SilentlyContinue; "
     "[pscustomobject]@{cpu=[math]::Round($pr.CPU,2); threads=$pr.Threads.Count; "
     "mb=[math]::Round($pr.WorkingSet64/1MB,1)} | ConvertTo-Json -Compress" % p.pid],
    capture_output=True, text=True, timeout=120)
o['процесс'] = (проба.stdout or '').strip()
if os.path.exists(LOG):
    with open(LOG, encoding='utf-8', errors='replace') as f:
        o['лог'] = f.read()[-1200:]
o['файл_лога'] = LOG
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
