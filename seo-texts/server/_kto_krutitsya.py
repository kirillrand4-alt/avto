# -*- coding: utf-8 -*-
r"""Что за процесс roli_telefonov сейчас живёт и с каким ключом."""
import json
import subprocess

out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*roli_telefonov*'} | "
     "%{ '{0}|{1}|{2}' -f $_.ProcessId, $_.CreationDate, $_.CommandLine }"],
    capture_output=True, text=True, timeout=90)
print(json.dumps({'процессы': [s.strip()[:200] for s in
                               (out.stdout or '').splitlines() if s.strip()]},
                 ensure_ascii=False, indent=1))
