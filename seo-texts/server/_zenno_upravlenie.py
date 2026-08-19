# -*- coding: utf-8 -*-
"""Есть ли управляющий шаблон/канал у Зенки: файлы, команды, задачи ZennoPoster."""
import io
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ZENNO = r'C:\seostat\drop\zenno'
итог = {}
итог['состав_zenno'] = []
for имя in sorted(os.listdir(ZENNO)):
    п = os.path.join(ZENNO, имя)
    итог['состав_zenno'].append({
        'имя': имя, 'папка': os.path.isdir(п),
        'размер': (os.path.getsize(п) if os.path.isfile(п) else None),
        'изменён': time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(п)))})
# файлы, похожие на управление
итог['похоже_на_команды'] = [x['имя'] for x in итог['состав_zenno']
                             if re.search(r'komand|upravl|control|task|zadan|start|stop',
                                          x['имя'], re.I)]
# проекты ZennoPoster
проекты = []
for корень in (r'C:\zenno', r'C:\seostat\zenno', os.path.expandvars(r'%USERPROFILE%\Documents'),
               r'C:\Users\Administrator\Desktop'):
    if not os.path.isdir(корень):
        continue
    for d, ds, fs in os.walk(корень):
        ds[:] = [x for x in ds if not x.startswith('.')][:6]
        for f in fs:
            if f.endswith('.xmlz') or f.endswith('.zp'):
                проекты.append(os.path.join(d, f)[:110])
        if len(проекты) > 20:
            break
итог['проекты_zenno'] = проекты[:12]
# что запущено под ZennoPoster
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'Zenno'} | "
                    "Select-Object Name,ProcessId,CommandLine | ConvertTo-Json"],
                   capture_output=True, text=True, timeout=180)
итог['процессы'] = (p.stdout or '')[:700]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
