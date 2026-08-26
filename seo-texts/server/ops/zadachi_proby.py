# -*- coding: utf-8 -*-
import subprocess
out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-ScheduledTask | Where-Object { $_.TaskName -match 'prob|проб|sender|sverk' } | "
     "ForEach-Object { $_.TaskName + ' | ' + $_.State + ' | ' + "
     "(($_.Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments }) -join '; ') }"],
    capture_output=True, text=True, timeout=90)
print((out.stdout or "").strip()[:2500] or "задач не нашлось")
