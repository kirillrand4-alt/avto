# -*- coding: utf-8 -*-
r"""Что реально стоит и что осталось живым."""
import json
import os
import subprocess

d = {'флаги': {}}
for флаг in ('HOLD-FAKTY.flag', 'HOLD-POISK.flag'):
    п = os.path.join(r'C:\sender\server', флаг)
    d['флаги'][флаг] = os.path.exists(п)
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "%{ '{0}|{1}' -f $_.ProcessId, $_.CommandLine } | "
     "Select-String -Pattern 'fakty_cikl|enrich_contacts|poisk_saytov|zenno_most' "
     '| %{ $_.ToString().Trim() }'],
    capture_output=True, text=True, timeout=120)
d['процессы'] = [s.strip()[:110] for s in (out.stdout or '').splitlines() if s.strip()]
print(json.dumps(d, ensure_ascii=False, indent=1))
