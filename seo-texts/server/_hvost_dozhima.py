# -*- coding: utf-8 -*-
"""Хвост лога дожима + сколько наших адресов сейчас в задании на дропе."""
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
п = r'C:\sender\server\probe-dozhim.log'
if os.path.exists(п):
    итог['лог'] = io.open(п, encoding='utf-8', errors='replace').read()[-500:]
env = {}
for l in open(r'C:\sender\server\runner-secrets.env', encoding='utf-8'):
    if '=' in l and not l.strip().startswith('#'):
        k, v = l.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
r = subprocess.run(['curl', '-s', '-H', 'X-Drop-Token: ' + env['DROP_TOKEN'],
                    env['DROP_URL'].rstrip('/') + '/probe-zadanie.json'],
                   capture_output=True, text=True, timeout=120).stdout
try:
    итог['в_задании'] = len(json.loads(r or '[]'))
except Exception:  # noqa: BLE001
    итог['в_задании'] = (r or '')[:80]
print(json.dumps(итог, ensure_ascii=False, indent=1))
