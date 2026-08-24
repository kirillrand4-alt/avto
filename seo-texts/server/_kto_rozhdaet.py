# -*- coding: utf-8 -*-
r"""Кто поднимает enrich_contacts: смотрим родителя процесса."""
import json
import subprocess

out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -like "
     "'*enrich_contacts*'} | %{ $p=$_; $r=Get-CimInstance Win32_Process "
     "-Filter \"ProcessId=$($p.ParentProcessId)\"; "
     "'{0}|{1}|родитель {2}|{3}' -f $p.ProcessId, $p.CreationDate, "
     "$p.ParentProcessId, ($r.CommandLine -replace '.*\\\\','') }"],
    capture_output=True, text=True, timeout=120)
d = {'процессы': [s.strip()[:150] for s in (out.stdout or '').splitlines()
                  if s.strip()]}
оч = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process | %{ $_.CommandLine } | Select-String "
     "-Pattern 'job_runner|enrich_panel|storozh' | %{ $_.ToString().Trim() }"],
    capture_output=True, text=True, timeout=120)
d['рядом'] = [s.strip()[-70:] for s in (оч.stdout or '').splitlines() if s.strip()][:6]
print(json.dumps(d, ensure_ascii=False, indent=1)[:1600])
