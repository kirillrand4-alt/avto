# -*- coding: utf-8 -*-
r"""Добить оставшийся enrich_contacts: он начат до холда и всё ещё зовёт провайдера."""
import json
import subprocess
import time

было = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*enrich_contacts*'} | "
     "%{ '{0}|{1}' -f $_.ProcessId, $_.CreationDate }"],
    capture_output=True, text=True, timeout=120)
d = {'было': [s.strip() for s in (было.stdout or '').splitlines() if s.strip()]}
subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*enrich_contacts*'} | "
     '%{ Stop-Process -Id $_.ProcessId -Force }'],
    capture_output=True, text=True, timeout=120)
time.sleep(6)
стало = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "%{ $_.CommandLine } | Select-String -Pattern "
     "'fakty_cikl|enrich_contacts|poisk_saytov' | %{ $_.ToString().Trim() }"],
    capture_output=True, text=True, timeout=120)
d['осталось'] = [s.strip()[-60:] for s in (стало.stdout or '').splitlines()
                 if s.strip()]
print(json.dumps(d, ensure_ascii=False, indent=1))
