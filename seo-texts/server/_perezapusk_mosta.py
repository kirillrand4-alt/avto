# -*- coding: utf-8 -*-
r"""Перезапуск моста Зенки: он держит код в памяти с момента старта.

Гасим только процесс с «--demon» и поднимаем той же рукой сторожа — с его
окружением и логом, чтобы ничего не разъехалось.
"""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
import storozh as S  # noqa: E402

d = {}
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*zenno_most*--demon*'} | "
     '%{ Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }'],
    capture_output=True, text=True, timeout=120)
d['погашено'] = [s.strip() for s in (out.stdout or '').split() if s.strip()]
time.sleep(3)
d['pid'] = S._поднять('zenno_most.py', ['--demon', '120'],
                      os.path.join(DIR, 'zenno_most.log'))
time.sleep(15)
d['жив'] = S._крутится(S._живые(), 'zenno_most.py', '--demon')
print(json.dumps(d, ensure_ascii=False))
