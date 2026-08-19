# -*- coding: utf-8 -*-
"""Живые исходники фронта, наличие node/npm и где лента лидов в коде."""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
for к in (r'C:\sender\sender\web', r'C:\sender\web'):
    if not os.path.exists(к):
        итог[к] = 'нет'
        continue
    состав = sorted(os.listdir(к))[:15]
    итог[к] = {'состав': состав}
    src = os.path.join(к, 'src')
    if os.path.exists(src):
        файлы = []
        for d, ds, fs in os.walk(src):
            ds[:] = [x for x in ds if x != 'node_modules']
            for f in fs:
                файлы.append(os.path.relpath(os.path.join(d, f), src))
        итог[к]['src'] = {'файлов': len(файлы),
                          'про_лиды': [x for x in файлы if 'lead' in x.lower()
                                       or 'lid' in x.lower()][:10],
                          'примеры': файлы[:12]}
for exe in ('node', 'npm'):
    p = subprocess.run(['where', exe], capture_output=True, text=True)
    итог['есть_' + exe] = (p.stdout or '').strip().splitlines()[:1] or 'нет'
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
