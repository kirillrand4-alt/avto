# -*- coding: utf-8 -*-
r"""Идёт ли работа: процессорное время процесса сбора за 20 секунд."""
import json
import subprocess
import time


def снять():
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-Process python -ErrorAction SilentlyContinue | "
         "Where-Object {$_.Id -eq %d} | %%{ '{0}|{1}' -f $_.CPU, $_.WorkingSet }"
         % 297820], capture_output=True, text=True, timeout=90)
    return (out.stdout or '').strip()


a = снять()
time.sleep(20)
b = снять()
print(json.dumps({'было': a, 'стало': b}, ensure_ascii=False))
