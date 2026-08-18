# -*- coding: utf-8 -*-
"""Остановить старый дожим перед заменой."""
import json, subprocess, sys
sys.stdout.reconfigure(encoding='utf-8')
p = subprocess.run(['wmic', 'process', 'where',
                    "commandline like '%probe_dozhim%' and name like 'python%'",
                    'get', 'processid'], capture_output=True, text=True)
у = []
for x in (p.stdout or '').splitlines():
    if x.strip().isdigit():
        subprocess.run(['taskkill', '/PID', x.strip(), '/F'], capture_output=True)
        у.append(x.strip())
print(json.dumps({'убито': у}, ensure_ascii=False))
