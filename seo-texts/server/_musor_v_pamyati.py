# -*- coding: utf-8 -*-
"""Настоящий мусор в памяти: питон-процессы без дела и их возраст."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "ForEach-Object {[pscustomobject]@{pid=$_.ProcessId;"
                    "mb=[math]::Round($_.WorkingSet/1MB);"
                    "start=$_.CreationDate;cmd=$_.CommandLine}} | ConvertTo-Json -Depth 3"],
                   capture_output=True, text=True, timeout=180)
try:
    строки = json.loads(p.stdout or '[]')
except Exception:  # noqa: BLE001
    строки = []
из = []
for r in (строки if isinstance(строки, list) else [строки]):
    cmd = str(r.get('cmd') or '')[-90:]
    из.append({'pid': r.get('pid'), 'МБ': r.get('mb'), 'команда': cmd})
из.sort(key=lambda x: -(x['МБ'] or 0))
print(json.dumps({'питонов': len(из), 'всего_МБ': sum(x['МБ'] or 0 for x in из),
                  'список': из[:22]}, ensure_ascii=False, indent=1)[:3000])
