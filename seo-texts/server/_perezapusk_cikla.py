# -*- coding: utf-8 -*-
r"""Перезапуск вечного цикла фактов, чтобы он подхватил новый site_facts.

fakty_cikl.py — процесс с «while True», он импортирует site_facts ОДИН раз при
старте. Выложенный на диск файл живой процесс не видит: правку 20.08 (переразбор
устаревших паспортов и склейка при записи) он бы не заметил никогда. Поэтому
цикл гасим и поднимаем той же рукой, что и сторож, — с его окружением и логом.
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
лог = r'C:\sender\server\fakty_cikl.log'
if os.path.exists(лог):
    with open(лог, encoding='utf-8', errors='replace') as f:
        хвост = [s.strip() for s in f if s.strip()][-4:]
    d['круги_до'] = [s[:190] for s in хвост]

# 1. Кто крутится сейчас.
было = S._живые()
d['цикл_был_жив'] = S._крутится(было, 'fakty_cikl.py')

# 2. Гасим только fakty_cikl.py — по командной строке, а не по имени python.
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*fakty_cikl.py*'} | "
     '%{ Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }'],
    capture_output=True, text=True, timeout=120)
d['погашено'] = [s.strip() for s in (out.stdout or '').split() if s.strip()]

# 3. Поднимаем так же, как это делает сторож: то же окружение и тот же лог.
time.sleep(3)
if os.path.exists(os.path.join(DIR, 'HOLD-FAKTY.flag')):
    d['НЕ_ПОДНЯЛИ'] = 'лежит HOLD-FAKTY.flag — цикл под холдом владельца'
else:
    d['pid'] = S._поднять('fakty_cikl.py', [], лог, S._sreda_faktov())
    time.sleep(20)
    d['цикл_жив_после'] = S._крутится(S._живые(), 'fakty_cikl.py')
print(json.dumps(d, ensure_ascii=False, indent=1))
