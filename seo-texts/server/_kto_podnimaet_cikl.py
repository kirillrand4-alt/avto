# -*- coding: utf-8 -*-
"""Кто поднимает fakty_cikl: шапка самого файла, все задания планировщика,
сторожа среди процессов. Ничего не убиваем — только смотрим."""
import io
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
try:
    т = io.open(r'C:\sender\server\fakty_cikl.py', encoding='utf-8',
                errors='replace').read()
    итог['fakty_cikl_шапка'] = т[:1100]
    итог['fakty_cikl_строк'] = len(т.splitlines())
except Exception as e:  # noqa: BLE001
    итог['fakty_cikl_шапка'] = 'нет файла: %s' % e
t = subprocess.run(['schtasks', '/query', '/fo', 'csv', '/nh'],
                   capture_output=True, text=True)
итог['задания_все'] = sorted({l.split('","')[0].strip('"') for l in
                              (t.stdout or '').splitlines()
                              if l.startswith('"\\') and '\\Microsoft\\' not in l})
p = subprocess.run(['wmic', 'process', 'where', "name like 'python%'",
                    'get', 'processid,commandline', '/format:list'],
                   capture_output=True, text=True)
итог['сторожа'] = [l.strip()[-140:] for l in (p.stdout or '').splitlines()
                   if 'CommandLine=' in l and any(k in l.lower() for k in
                   ('storozh', 'dozor', 'zdorov', 'watch', 'cikl'))]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:5000])
