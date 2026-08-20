# -*- coding: utf-8 -*-
r"""Мост зенки: жив ли демон разбора и почему копится gotovo."""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
ZENNO = r'C:\seostat\drop\zenno'
GOTOVO = os.path.join(ZENNO, 'gotovo')
RAZOBRANO = os.path.join(ZENNO, 'razobrano')

итог = {}
try:
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "%{ $_.ProcessId.ToString() + ' | ' + "
         "($_.CommandLine -replace '.*\\\\','') + ' | ' + "
         "[int]($_.WorkingSetSize/1MB) + 'MB' }"],
        capture_output=True, text=True, timeout=90)
    итог['питоны'] = [x.strip() for x in out.stdout.splitlines() if x.strip()][:20]
except Exception as e:  # noqa: BLE001
    итог['питоны'] = str(e)[:100]


def возраст(п):
    try:
        имена = os.listdir(п)
    except OSError:
        return {}
    if not имена:
        return {'файлов': 0}
    св, ст = 0, 1e18
    т = time.time()
    for и in имена[:4000]:
        try:
            m = os.path.getmtime(os.path.join(п, и))
        except OSError:
            continue
        св = max(св, m)
        ст = min(ст, m)
    return {'файлов': len(имена),
            'самый_свежий_мин_назад': round((т - св) / 60, 1),
            'самый_старый_мин_назад': round((т - ст) / 60, 1)}


итог['gotovo'] = возраст(GOTOVO)
итог['razobrano'] = возраст(RAZOBRANO)
for имя in ('demon.out', 'zhurnal.txt'):
    p = os.path.join(ZENNO, имя)
    if os.path.exists(p):
        with open(p, encoding='utf-8', errors='replace') as f:
            итог[имя] = f.read()[-600:]
p = r'C:\sender\server\storozh.jsonl'
if os.path.exists(p):
    with open(p, encoding='utf-8', errors='replace') as f:
        итог['сторож_хвост'] = [s.strip() for s in f][-3:]
print(json.dumps(итог, ensure_ascii=False, indent=1))
