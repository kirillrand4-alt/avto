# -*- coding: utf-8 -*-
"""Сколько потоков у ZennoPoster и что он сейчас делает."""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-Process ZennoPoster -ErrorAction SilentlyContinue | "
                    "Select-Object Id,StartTime,CPU,WorkingSet | ConvertTo-Json"],
                   capture_output=True, text=True, timeout=180)
итог['процессы'] = (p.stdout or '')[:500]
# настройки: ищем конфиги с числом потоков
кандидаты = []
for корень in (os.path.expandvars(r'%APPDATA%\ZennoLab'),
               os.path.expandvars(r'%PROGRAMDATA%\ZennoLab'),
               r'C:\Program Files (x86)\ZennoLab', r'C:\zenno'):
    if not os.path.isdir(корень):
        continue
    for d, ds, fs in os.walk(корень):
        ds[:] = [x for x in ds if 'log' not in x.lower()][:8]
        for f in fs:
            if f.endswith(('.xml', '.config', '.json')) and len(кандидаты) < 40:
                кандидаты.append(os.path.join(d, f))
итог['конфигов_найдено'] = len(кандидаты)
потоки = []
for п in кандидаты:
    try:
        t = io.open(п, encoding='utf-8', errors='replace').read()
    except Exception:  # noqa: BLE001
        continue
    for м in re.finditer(r'[Tt]hread[s]?\w*"?\s*[=:>]\s*"?(\d{1,3})', t):
        потоки.append({'файл': os.path.basename(п), 'значение': м.group(1)})
итог['упоминания_потоков'] = потоки[:10]
c = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "(Get-CimInstance Win32_Processor | Measure-Object -Property "
                    "LoadPercentage -Average).Average"],
                   capture_output=True, text=True, timeout=120)
итог['загрузка_cpu'] = (c.stdout or '').strip()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2200])
