# -*- coding: utf-8 -*-
"""Остановить судью доменов (питон-процессы с prigovor_domenov в команде)."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
p = subprocess.run(['wmic', 'process', 'where',
                    "commandline like '%prigovor_domenov%' and name like 'python%'",
                    'get', 'processid'], capture_output=True, text=True)
пиды = [x.strip() for x in (p.stdout or '').splitlines()
        if x.strip().isdigit()]
убито = []
for pid in пиды:
    subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
    убито.append(pid)
print(json.dumps({'убито': убито}, ensure_ascii=False))
