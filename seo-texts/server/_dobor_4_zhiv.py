# -*- coding: utf-8 -*-
"""Жив ли процесс добора и что в логе."""
import os
import subprocess
import time

LOG = r'C:\sender\_tmp\kesh-dobor.out'
if os.path.exists(LOG):
    print('лог, изменён', time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(LOG))))
    print(open(LOG, encoding='utf-8', errors='replace').read()[-1500:])
try:
    out = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get',
                          'ProcessId,CommandLine'], capture_output=True, text=True,
                         timeout=60).stdout
    for s in out.splitlines():
        if 'dobor' in s.lower():
            print('ПРОЦЕСС:', s.strip()[:140])
except Exception as e:  # noqa: BLE001
    print('процессы:', str(e)[:100])
z = r'C:\sender\_tmp\kesh-dobor.jsonl'
print('журнал:', os.path.getsize(z) if os.path.exists(z) else 'нет файла')
