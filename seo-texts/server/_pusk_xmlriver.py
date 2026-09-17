# -*- coding: utf-8 -*-
r"""Прогон новостного скана по xmlriver (85 региональных запросов, два движка).

Запуск как у рабочего прогона: python напрямую, файлы дескрипторами — cmd с
отсоединением не отдаёт stdin (проверено 16.09, полтора часа простоя).
"""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
МЕТКА = time.strftime('%d%m-%H%M')
ARGS = os.path.join(DIR, 'xmlriver_args_%s.json' % МЕТКА)
LOG = os.path.join(DIR, 'xmlriver_scan_%s.log' % МЕТКА)

args = {
    'collectors': ['xmlriver'],
    'xmlriver_engines': ['google', 'yandex'],
    'days': 45,
    'max_items': 8,
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
                     stdin=вход, stdout=выход, stderr=subprocess.STDOUT, close_fds=False)
вход.close()
выход.close()
time.sleep(60)

проба = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$pr = Get-Process -Id %d -ErrorAction SilentlyContinue; "
     "if ($pr) { [math]::Round($pr.CPU,1) } else { 'процесс завершился' }" % p.pid],
    capture_output=True, text=True, timeout=90)
o = {'pid': p.pid, 'аргументы': args, 'лог': os.path.basename(LOG),
     'cpu_через_60с': (проба.stdout or '').strip(),
     'лог_байт': os.path.getsize(LOG) if os.path.exists(LOG) else None}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
