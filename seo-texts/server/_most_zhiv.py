# -*- coding: utf-8 -*-
r"""Жив ли мост после перезапуска и куда он пишет."""
import json
import os
import subprocess
import time

d = {}
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*zenno_most*'} | "
     "%{ '{0}|{1}|{2}' -f $_.ProcessId, $_.CreationDate, $_.CommandLine }"],
    capture_output=True, text=True, timeout=120)
d['процессы'] = [s.strip()[:160] for s in (out.stdout or '').splitlines() if s.strip()]
for п in (r'C:\seostat\drop\zenno\demon.out', r'C:\sender\server\zenno_most.log'):
    if os.path.exists(п):
        d[os.path.basename(п)] = {
            'байт': os.path.getsize(п),
            'обновлён_сек_назад': int(time.time() - os.path.getmtime(п))}
        with open(п, encoding='utf-8', errors='replace') as f:
            хв = [s.strip() for s in f if s.strip()][-2:]
        d[os.path.basename(п)]['хвост'] = [s[:150] for s in хв]
print(json.dumps(d, ensure_ascii=False, indent=1)[:2200])
