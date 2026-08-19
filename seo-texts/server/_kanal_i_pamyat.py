# -*- coding: utf-8 -*-
"""Файл команд для шаблона-управленца + память по группам процессов."""
import io
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ZENNO = r'C:\seostat\drop\zenno'
итог = {'файлы_zenno': []}
for имя in sorted(os.listdir(ZENNO)):
    п = os.path.join(ZENNO, имя)
    if os.path.isfile(п):
        итог['файлы_zenno'].append('%s (%d б, %s)' % (
            имя, os.path.getsize(п),
            time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(п)))))
# кто пишет vypolneno — ищем в коде сервера упоминания
места = []
for корень in (r'C:\sender\server', r'C:\seostat\drop'):
    for d, ds, fs in os.walk(корень):
        ds[:] = [x for x in ds if x not in ('razobrano', 'gotovo', 'snimki',
                                            'pagecache', '__pycache__')]
        for f in fs:
            if not f.endswith(('.py', '.txt', '.md')):
                continue
            try:
                t = io.open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if 'vypolneno' in t or 'potoki ' in t:
                места.append(os.path.join(d, f)[:90])
итог['кто_знает_про_vypolneno'] = места[:8]
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-Process | Group-Object ProcessName | ForEach-Object "
                    "{[pscustomobject]@{n=$_.Name;c=$_.Count;"
                    "mb=[math]::Round(($_.Group|Measure-Object WorkingSet -Sum).Sum/1MB)}} | "
                    "Sort-Object mb -Descending | Select-Object -First 14 | ConvertTo-Json"],
                   capture_output=True, text=True, timeout=180)
итог['память_по_группам'] = (p.stdout or '')[:1500]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3200])
