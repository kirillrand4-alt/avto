# -*- coding: utf-8 -*-
"""Что делает задание \\Storozh: команда, расписание, и текст его скрипта."""
import io
import json
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
t = subprocess.run(['schtasks', '/query', '/tn', '\\Storozh', '/v', '/fo', 'list'],
                   capture_output=True, text=True)
итог['задание'] = [l.strip() for l in (t.stdout or '').splitlines()
                   if any(k in l for k in ('Task To Run', 'Schedule', 'Repeat:',
                                           'Status', 'Run As User', 'Start In'))][:10]
m = re.search(r'Task To Run:\s*(.+)', t.stdout or '')
итог['команда'] = (m.group(1).strip() if m else '')
пути = re.findall(r'[A-Z]:\\[^\s"]+\.(?:py|bat|cmd|ps1)', итог['команда'])
for п in пути:
    try:
        итог['скрипт_' + п.split('\\')[-1]] = io.open(
            п, encoding='utf-8', errors='replace').read()[:2200]
    except Exception as e:  # noqa: BLE001
        итог['скрипт_' + п] = 'не прочитать: %s' % e
print(json.dumps(итог, ensure_ascii=False, indent=1)[:5200])
