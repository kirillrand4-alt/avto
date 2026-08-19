# -*- coding: utf-8 -*-
"""Чем занята оперативка и что в управляющих файлах Зенки."""
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "$os=Get-CimInstance Win32_OperatingSystem; "
                    "[pscustomobject]@{ВсегоГБ=[math]::Round($os.TotalVisibleMemorySize/1MB,1);"
                    "СвободноГБ=[math]::Round($os.FreePhysicalMemory/1MB,1)} | ConvertTo-Json"],
                   capture_output=True, text=True, timeout=180)
итог['память'] = (p.stdout or '').strip()[:200]
p2 = subprocess.run(['powershell', '-NoProfile', '-Command',
                     "Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 12 "
                     "Name,Id,@{n='МБ';e={[math]::Round($_.WorkingSet/1MB)}} | ConvertTo-Json"],
                    capture_output=True, text=True, timeout=180)
итог['топ_по_памяти'] = (p2.stdout or '')[:1400]
for имя in ('zenka-stoit.txt', 'vypolneno.txt', 'snimki_zadanie.txt'):
    п = os.path.join(r'C:\seostat\drop\zenno', имя)
    if os.path.exists(п):
        итог[имя] = io.open(п, encoding='utf-8', errors='replace').read()[:300]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2600])
