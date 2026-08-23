# -*- coding: utf-8 -*-
r"""Сколько мостов сейчас живёт и что в хвосте demon.out."""
import json
import os
import subprocess

d = {}
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*zenno_most*'} | "
     "%{ '{0}|{1}' -f $_.ProcessId, $_.CreationDate }"],
    capture_output=True, text=True, timeout=120)
d['мосты'] = [s.strip() for s in (out.stdout or '').splitlines() if s.strip()]
п = r'C:\seostat\drop\zenno\demon.out'
строки = [s.strip() for s in open(п, encoding='utf-8', errors='replace') if s.strip()]
d['хвост'] = [s[:120] for s in строки[-8:]]
print(json.dumps(d, ensure_ascii=False, indent=1)[:1800])
