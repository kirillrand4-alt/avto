# -*- coding: utf-8 -*-
"""Что сейчас крутится и жжёт провайдера: питон-процессы и задания планировщика."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
p = subprocess.run(['wmic', 'process', 'where', "name like 'python%'",
                    'get', 'processid,commandline', '/format:list'],
                   capture_output=True, text=True)
процессы = []
для = {}
for l in (p.stdout or '').splitlines():
    l = l.strip()
    if l.startswith('CommandLine='):
        для['cmd'] = l[12:][-160:]
    elif l.startswith('ProcessId='):
        для['pid'] = l[10:]
        if для.get('cmd'):
            процессы.append(dict(для))
        для = {}
итог['питоны'] = процессы
t = subprocess.run(['schtasks', '/query', '/fo', 'csv'],
                   capture_output=True, text=True)
итог['задания'] = [l.split('","')[0].strip('"') for l in (t.stdout or '').splitlines()
                   if any(k in l.lower() for k in
                          ('sender', 'enrich', 'site', 'fact', 'news', 'poisk',
                           'zenno', 'обход', 'pereobhod', 'dolив', 'doliv'))][:20]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:5200])
