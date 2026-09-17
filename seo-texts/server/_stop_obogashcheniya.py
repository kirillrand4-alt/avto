# -*- coding: utf-8 -*-
"""Погасить прогон: классификация закончена, обогащение контактами владельцу не нужно."""
import json, subprocess, time

o = {}
было = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'} | "
     'Select-Object ProcessId | ConvertTo-Json -Compress'],
    capture_output=True, text=True, timeout=90)
o['было'] = (было.stdout or '').strip()[:160]
k = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'} | "
     '%{ Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }'],
    capture_output=True, text=True, timeout=90)
o['погашено'] = [s.strip() for s in (k.stdout or '').split() if s.strip()]
time.sleep(3)
ост = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'}).ProcessId | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o['осталось'] = (ост.stdout or '').strip()[:120] or 'пусто'
import sqlite3
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
o['сигналов'] = c.execute('select count(*) from signals').fetchone()[0]
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
