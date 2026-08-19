# -*- coding: utf-8 -*-
r"""Откуда процессы на сервере берут XMLRIVER_USER/KEY — и видит ли их сторож."""
import json
import os
import subprocess

итог = {'в_моём_окружении': {
    'XMLRIVER_USER': (os.environ.get('XMLRIVER_USER') or '')[:6] + '…'
    if os.environ.get('XMLRIVER_USER') else '',
    'XMLRIVER_KEY_есть': bool(os.environ.get('XMLRIVER_KEY'))}}

# машинные переменные (их видит служба/планировщик, а не только моя сессия)
try:
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "[Environment]::GetEnvironmentVariable('XMLRIVER_USER','Machine');"
         "if([Environment]::GetEnvironmentVariable('XMLRIVER_KEY','Machine')){'KEY-MACHINE-ЕСТЬ'}"
         "else{'KEY-MACHINE-НЕТ'};"
         "[Environment]::GetEnvironmentVariable('XMLRIVER_USER','User');"
         "if([Environment]::GetEnvironmentVariable('XMLRIVER_KEY','User')){'KEY-USER-ЕСТЬ'}"
         "else{'KEY-USER-НЕТ'}"],
        capture_output=True, text=True, timeout=60)
    итог['машинные'] = [x for x in out.stdout.splitlines() if x.strip()]
except Exception as e:  # noqa: BLE001
    итог['машинные'] = str(e)[:100]

# файлы, где ключ мог быть прописан
файлы = {}
for p in (r'C:\sender\.env', r'C:\sender\server\.env', r'C:\sender\sender.yaml',
          r'C:\sender\server\kluchi.json', r'C:\sender\kluchi.json',
          r'C:\sender\server\sreda.json'):
    if os.path.exists(p):
        try:
            t = open(p, encoding='utf-8', errors='replace').read()
            файлы[p] = [s.split('=')[0].split(':')[0].strip()
                        for s in t.splitlines() if 'XMLRIVER' in s.upper()]
        except Exception as e:  # noqa: BLE001
            файлы[p] = str(e)[:80]
итог['файлы'] = файлы

# как запускается сторож
try:
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-ScheduledTask | Where-Object {$_.TaskName -like '*torozh*' -or "
         "$_.TaskName -like '*Storozh*' -or $_.TaskName -like '*Probe*'} | "
         "%{ $_.TaskName + ' | ' + $_.Principal.UserId + ' | ' + "
         "($_.Actions | %{$_.Execute + ' ' + $_.Arguments}) }"],
        capture_output=True, text=True, timeout=60)
    итог['задачи_планировщика'] = [x.strip() for x in out.stdout.splitlines() if x.strip()]
except Exception as e:  # noqa: BLE001
    итог['задачи_планировщика'] = str(e)[:100]

print(json.dumps(итог, ensure_ascii=False, indent=1))
