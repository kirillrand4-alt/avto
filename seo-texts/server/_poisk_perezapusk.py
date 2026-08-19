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
живые = S._живые()
пиды = [p for p in живые if 'poisk_saytov.py' in (p.get('cmd') or '')] \
    if isinstance(живые, list) else []
итог['было_живых'] = len(пиды)
subprocess.run(['taskkill', '/F', '/FI', 'IMAGENAME eq python.exe',
                '/FI', 'WINDOWTITLE eq poisk*'], capture_output=True, timeout=60)
# надёжнее — по командной строке
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
