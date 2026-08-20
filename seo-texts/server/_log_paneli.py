# -*- coding: utf-8 -*-
r"""Хвост лога панели: ищем трассировку падения /lid/…"""
import json
import os
import subprocess

d = {}
кандидаты = [r'C:\sender\panel.log', r'C:\sender\serve-api.out',
             r'C:\sender\sender\panel.log', r'C:\sender\panel.out',
             r'C:\sender\logs\panel.log']
for п in кандидаты:
    if os.path.exists(п):
        d.setdefault('файлы', {})[п] = os.path.getsize(п)

# nssm пишет вывод службы туда, куда настроен — спросим саму службу
try:
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "$k='HKLM:\\SYSTEM\\CurrentControlSet\\Services\\SenderPanel\\Parameters';"
         "if(Test-Path $k){(Get-ItemProperty $k) | "
         "Select-Object AppStdout,AppStderr,AppDirectory,AppParameters | "
         "ConvertTo-Json -Compress}else{'нет ключа'}"],
        capture_output=True, text=True, timeout=90)
    d['служба'] = (out.stdout or '').strip()[:600]
except Exception as e:  # noqa: BLE001
    d['служба'] = str(e)[:120]

путь = ''
try:
    j = json.loads(d.get('служба') or '{}')
    путь = j.get('AppStderr') or j.get('AppStdout') or ''
except Exception:  # noqa: BLE001
    pass
if путь and os.path.exists(путь):
    with open(путь, encoding='utf-8', errors='replace') as f:
        текст = f.read()
    d['лог'] = путь
    i = текст.rfind('Traceback')
    d['хвост'] = текст[i:i + 1800] if i >= 0 else текст[-1200:]
print(json.dumps(d, ensure_ascii=False, indent=1)[:3000])
