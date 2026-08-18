# -*- coding: utf-8 -*-
"""Добить enrich_contacts: пиды, результат taskkill дословно, все задания
планировщика (ищем сторожа, который их перезапускает)."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {'до': [], 'taskkill': [], 'после': [], 'задания_все': []}


def пиды():
    p = subprocess.run(['wmic', 'process', 'where',
                        "commandline like '%enrich_contacts%' and name like 'python%'",
                        'get', 'processid'], capture_output=True, text=True)
    return [x.strip() for x in (p.stdout or '').splitlines() if x.strip().isdigit()]


итог['до'] = пиды()
for pid in итог['до']:
    r = subprocess.run(['taskkill', '/PID', pid, '/F', '/T'],
                       capture_output=True, text=True)
    итог['taskkill'].append({'pid': pid, 'rc': r.returncode,
                             'out': (r.stdout or r.stderr or '').strip()[:120]})
итог['после'] = пиды()
t = subprocess.run(['schtasks', '/query', '/fo', 'csv', '/nh'],
                   capture_output=True, text=True)
итог['задания_все'] = sorted({l.split('","')[0].strip('"') for l in
                              (t.stdout or '').splitlines()
                              if l.startswith('"\\') and '\\Microsoft\\' not in l})[:40]
print(json.dumps(итог, ensure_ascii=False, indent=1))
