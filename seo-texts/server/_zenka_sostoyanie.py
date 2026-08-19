# -*- coding: utf-8 -*-
"""Что сейчас с Зенкой: очередь, кэш, процессы, загрузка сервера, база сайтов."""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ZENNO = r'C:\seostat\drop\zenno'
KESH = r'C:\seostat\drop\pagecache'
итог = {}
for имя, п in (('очередь', os.path.join(ZENNO, 'ochered.txt')),
               ('отдано', os.path.join(ZENNO, 'otdano.txt'))):
    итог[имя] = sum(1 for l in open(п, encoding='utf-8', errors='replace')
                    if l.strip()) if os.path.exists(п) else 'нет файла'
итог['в_кэше'] = len([x for x in os.listdir(KESH) if x.endswith('.json.gz')])
итог['в_gotovo'] = len(os.listdir(os.path.join(ZENNO, 'gotovo'))) \
    if os.path.isdir(os.path.join(ZENNO, 'gotovo')) else 0
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-Process | Where-Object {$_.ProcessName -match 'Zenno|python|chrome'} | "
                    "Group-Object ProcessName | Select-Object Name,Count | ConvertTo-Json"],
                   capture_output=True, text=True, timeout=180)
итог['процессы'] = (p.stdout or '')[:400]
c = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage "
                    "-Average).Average; (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors"],
                   capture_output=True, text=True, timeout=180)
итог['загрузка_и_ядра'] = (c.stdout or '').split()
# сколько сайтов известно
import sqlite3
e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
итог['enrich_с_сайтом'] = e.execute(
    "select count(*) from companies where coalesce(site,'')<>'' "
    "or coalesce(cand_site,'')<>''").fetchone()[0]
e.close()
for путь in (r'C:\sender\obzvon-index.db', r'C:\seostat\app\obzvon-index.db',
             r'C:\sender\server\obzvon-index.db'):
    if os.path.exists(путь):
        итог['обзвон_база'] = путь
        o = sqlite3.connect('file:%s?mode=ro' % путь.replace('\\', '/'), uri=True)
        итог['обзвон_таблицы'] = [r[0] for r in o.execute(
            "select name from sqlite_master where type='table'")][:8]
        try:
            итог['обзвон_с_сайтом'] = o.execute(
                "select count(*) from obzvon where coalesce(sites,'')<>''").fetchone()[0]
            итог['обзвон_всего'] = o.execute('select count(*) from obzvon').fetchone()[0]
        except Exception as ex:  # noqa: BLE001
            итог['обзвон_ошибка'] = str(ex)[:100]
        o.close()
        break
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2500])
