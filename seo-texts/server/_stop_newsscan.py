# -*- coding: utf-8 -*-
"""Выключить NewsScan: задание планировщика в disable + добить живой процесс."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
r = subprocess.run(['schtasks', '/change', '/tn', '\\RuspromNewsScan', '/disable'],
                   capture_output=True, text=True)
итог['disable'] = {'rc': r.returncode, 'out': (r.stdout or r.stderr or '').strip()[:120]}
q = subprocess.run(['schtasks', '/query', '/tn', '\\RuspromNewsScan', '/fo', 'list'],
                   capture_output=True, text=True)
итог['статус_задания'] = [l.strip() for l in (q.stdout or '').splitlines()
                          if 'Status' in l or 'Next Run' in l]
p = subprocess.run(['wmic', 'process', 'where',
                    "commandline like '%news_scan%' and name like 'python%'",
                    'get', 'processid'], capture_output=True, text=True)
итог['убито_news_scan'] = []
for x in (p.stdout or '').splitlines():
    if x.strip().isdigit():
        k = subprocess.run(['taskkill', '/PID', x.strip(), '/F'],
                           capture_output=True, text=True)
        итог['убито_news_scan'].append({'pid': x.strip(), 'rc': k.returncode})
print(json.dumps(итог, ensure_ascii=False, indent=1))
