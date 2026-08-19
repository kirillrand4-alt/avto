# -*- coding: utf-8 -*-
r"""Перезапустить прогон поиска, чтобы он подхватил новый код.

Процесс поднят до выкладки правок и работает по старой логике (один адрес из
выдачи вместо перебора). Гасим его и поднимаем заново через сторож.
"""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
import storozh as S  # noqa: E402

итог = {}
итог['крутился_до'] = bool(S._крутится(S._живые(), 'poisk_saytov.py'))
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object {$_.CommandLine -like '*poisk_saytov.py*'} | "
     "%{ Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
    capture_output=True, text=True, timeout=90)
итог['погашено'] = [x.strip() for x in out.stdout.split() if x.strip()]
time.sleep(4)
итог['сторож'] = S.обход()
time.sleep(15)
итог['крутится'] = bool(S._крутится(S._живые(), 'poisk_saytov.py'))
print(json.dumps(итог, ensure_ascii=False, indent=1))
