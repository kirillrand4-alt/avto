# -*- coding: utf-8 -*-
"""Статус пилота Meyer: последние логи пилота, число строк в журналах, живые процессы python с pilot в командной строке."""
import glob
import json
import os
import subprocess

DIR = r'C:\sender\server'
o = {}
for п in ('pilot-serp.jsonl', 'pilot-razbor.jsonl', 'pilot-spisok.json', 'pilot-kontakty.jsonl', 'pilot-audit.jsonl',
          'pilot-audit2.jsonl', 'pilot-sayt-proverka.jsonl', 'pilot-glubokiy.jsonl', 'pilot-glubokiy2.jsonl',
          'pilot-reestr.json', 'pilot-oprov.jsonl', 'pilot-konveyer.json'):
    ф = os.path.join(DIR, п)
    if os.path.exists(ф):
        o[п] = sum(1 for _ in open(ф, encoding='utf-8', errors='replace'))
логи = sorted(glob.glob(os.path.join(DIR, '*pilot*.log')), key=os.path.getmtime)[-3:]
for л in логи:
    with open(л, encoding='utf-8', errors='replace') as f:
        o['лог ' + os.path.basename(л)] = f.read()[-700:]
try:
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*pilot*' "
                        "-and $_.CommandLine -notlike '*_status_pilot*' } | ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"],
                       capture_output=True, text=True, timeout=60)
    o['процессы'] = [x[-90:] for x in r.stdout.splitlines() if x.strip()]
except Exception as e:  # noqa: BLE001
    o['процессы'] = repr(e)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
