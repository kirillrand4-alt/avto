# -*- coding: utf-8 -*-
r"""Сколько у Зенки процессов, сколько каждый ест и что с памятью.

Перед тем как поднимать потоки, надо знать цену одного: ZennoPoster держит по
процессу на инстанс браузера, и упереться можно и в память, и в диск.
"""
import json
import subprocess

d = {}
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-Process | Where-Object {$_.ProcessName -match "
     "'Zenno|zbe|chrome|chromedriver|instance_cr'} | "
     "Group-Object ProcessName | %{ '{0}|{1}|{2:N0}' -f $_.Name, $_.Count, "
     "(($_.Group | Measure-Object WorkingSet64 -Sum).Sum/1MB) }"],
    capture_output=True, text=True, timeout=120)
d['процессы'] = [s.strip() for s in (out.stdout or '').splitlines() if s.strip()]
out2 = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$os=Get-CimInstance Win32_OperatingSystem;"
     "'{0}|{1}|{2}' -f [int]($os.FreePhysicalMemory/1024), "
     "[int]($os.TotalVisibleMemorySize/1024), "
     "[int]((Get-CimInstance Win32_PageFileUsage | "
     "Measure-Object CurrentUsage -Sum).Sum)"],
    capture_output=True, text=True, timeout=120)
ч = (out2.stdout or '').strip().split('|')
d['память'] = {'свободно_мб': ч[0] if ч else '?',
               'всего_мб': ч[1] if len(ч) > 1 else '?',
               'файл_подкачки_мб': ч[2] if len(ч) > 2 else '?'}
out3 = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage "
     '-Average).Average'], capture_output=True, text=True, timeout=120)
d['цп_проц'] = (out3.stdout or '').strip()
# настройки ZennoPoster, если лежат рядом
import os
for корень in (r'C:\Program Files (x86)\ZennoLab', r'C:\ZennoPoster',
               r'C:\seostat'):
    if os.path.isdir(корень):
        d.setdefault('каталоги', []).append(корень)
print(json.dumps(d, ensure_ascii=False, indent=1))
