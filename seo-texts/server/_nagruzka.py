# -*- coding: utf-8 -*-
r"""Нагрузка по группам: кто ест процессор и что при этом делает зенка.

Общий процент ничего не объясняет — важно, какая доля чья. Считаем по группам
процессов и рядом показываем, что за эту цену получаем.
"""
import json
import os
import subprocess
import time

ZENNO = r'C:\seostat\drop\zenno'
KESH = r'C:\seostat\drop\pagecache'
ГРУППЫ = {
    'зенка': ('zennoposter', 'zbe1', 'instance_cr_helper', 'base_cdp',
              'chromedriver'),
    'наши_питоны': ('python',),
    'антивирус': ('msmpeng', 'mssense', 'securityhealth'),
}
итог = {}
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "$c=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors;"
     "$a=Get-Counter '\\Process(*)\\% Processor Time' -ErrorAction SilentlyContinue;"
     "$a.CounterSamples | Where-Object {$_.InstanceName -notin @('_total','idle')} "
     "| %{ '{0}|{1:N2}' -f $_.InstanceName, ($_.CookedValue / $c) }"],
    capture_output=True, text=True, timeout=180)
по_группам, прочее = {}, 0.0
for стр in (out.stdout or '').splitlines():
    if '|' not in стр:
        continue
    имя, зн = стр.rsplit('|', 1)
    try:
        д = float(зн.strip().replace(',', '.'))
    except ValueError:
        continue
    имя = имя.strip().lower()
    для = None
    for г, префиксы in ГРУППЫ.items():
        if any(имя.startswith(п) for п in префиксы):
            для = г
            break
    if для:
        по_группам[для] = round(по_группам.get(для, 0.0) + д, 1)
    else:
        прочее += д
по_группам['прочее'] = round(прочее, 1)
итог['процессор_по_группам'] = dict(
    sorted(по_группам.items(), key=lambda x: -x[1]))

out2 = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "(Get-CimInstance Win32_Processor|Measure-Object LoadPercentage -Average).Average;"
     "(Get-CimInstance Win32_OperatingSystem|%{[int]($_.FreePhysicalMemory/1024)});"
     "(Get-CimInstance Win32_OperatingSystem|%{[int]($_.TotalVisibleMemorySize/1024)})"],
    capture_output=True, text=True, timeout=120)
ч = [x.strip() for x in out2.stdout.split() if x.strip()]
итог['машина'] = {'цп_проц': ч[0] if ч else '?',
                  'память_свободно_мб': ч[1] if len(ч) > 1 else '?',
                  'память_всего_мб': ч[2] if len(ч) > 2 else '?'}


def сколько(п, свежее_мин=None):
    порог = time.time() - (свежее_мин or 0) * 60
    n = 0
    try:
        with os.scandir(п) as it:
            for e in it:
                if not e.is_file():
                    continue
                if свежее_мин is None:
                    n += 1
                else:
                    try:
                        if e.stat().st_mtime >= порог:
                            n += 1
                    except OSError:
                        pass
    except OSError:
        return -1
    return n


оч = os.path.join(ZENNO, 'ochered.txt')
строк = 0
if os.path.exists(оч):
    with open(оч, encoding='utf-8-sig', errors='replace') as f:
        строк = sum(1 for s in f if s.strip())
итог['зенка'] = {'очередь': строк,
                 'gotovo': сколько(os.path.join(ZENNO, 'gotovo')),
                 'кэш': сколько(KESH), 'кэш_за_30мин': сколько(KESH, 30)}
д = os.path.join(ZENNO, 'demon.out')
if os.path.exists(д):
    хв = [s.strip() for s in open(д, encoding='utf-8', errors='replace')][-1:]
    итог['зенка']['последний_круг'] = [s[:200] for s in хв]
print(json.dumps(итог, ensure_ascii=False, indent=1))
