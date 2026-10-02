# -*- coding: utf-8 -*-
"""Жива ли цепочка Зенки: процессы, очередь, готовые, кэш страниц, журнал пульта."""
import glob
import json
import os
import subprocess
import time

SRV = r'C:\sender\server'
ZEN = r'C:\seostat\drop\zenno'
KESH = r'C:\seostat\drop\pagecache'
o = {'сейчас': time.strftime('%Y-%m-%d %H:%M:%S')}


def св(п):
    if not os.path.exists(п):
        return 'нет'
    st = os.stat(п)
    return {'байт': st.st_size,
            'изменён': time.strftime('%d.%m %H:%M', time.localtime(st.st_mtime)),
            'часов_назад': round((time.time() - st.st_mtime) / 3600, 1)}


def папка(п, маска='*'):
    if not os.path.isdir(п):
        return 'нет папки'
    ф = glob.glob(os.path.join(п, маска))
    if not ф:
        return {'файлов': 0}
    посл = max(ф, key=os.path.getmtime)
    return {'файлов': len(ф),
            'последний': os.path.basename(посл)[:40],
            'изменён': time.strftime('%d.%m %H:%M', time.localtime(os.path.getmtime(посл))),
            'часов_назад': round((time.time() - os.path.getmtime(посл)) / 3600, 1)}


for имя, п in (('ochered.txt', os.path.join(ZEN, 'ochered.txt')),
               ('komanda.txt', os.path.join(ZEN, 'komanda.txt')),
               ('dispetcher.json', os.path.join(ZEN, 'dispetcher.json')),
               ('vypolneno.txt', os.path.join(ZEN, 'vypolneno.txt')),
               ('ne_otkrylis.txt', os.path.join(ZEN, 'ne_otkrylis.txt'))):
    o.setdefault('файлы', {})[имя] = св(п)

for имя, п in (('gotovo', os.path.join(ZEN, 'gotovo')),
               ('pagecache', KESH),
               ('razobrano', os.path.join(ZEN, 'razobrano'))):
    o.setdefault('папки', {})[имя] = папка(п)

пс = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'Zenno|python' -and "
     "($_.CommandLine -like '*zenno*' -or $_.Name -like 'Zenno*')} | "
     "Select-Object Name,ProcessId,@{n='cl';e={$_.CommandLine.Substring(0,"
     "[Math]::Min(90,$_.CommandLine.Length))}} | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=120)
o['процессы'] = (пс.stdout or 'нет').strip()[:600]

пс2 = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "(Get-Process ZennoPoster,ZennoPosterPro -ErrorAction SilentlyContinue | "
     'Measure-Object).Count'],
    capture_output=True, text=True, timeout=90)
o['процессов_ZennoPoster'] = (пс2.stdout or '').strip()

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:3500])
