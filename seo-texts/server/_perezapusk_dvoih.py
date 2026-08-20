# -*- coding: utf-8 -*-
r"""Перезапустить мост зенки и поиск сайтов, чтобы оба взяли новый код.

Мост крутится с квадратичным priyom(), поиск — с версией без перебора выдачи.
Оба поднимает сторож, поэтому достаточно погасить и позвать его круг.
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


def погасить(маска):
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object {$_.CommandLine -like '*%s*'} | "
         "%%{ Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }" % маска],
        capture_output=True, text=True, timeout=90)
    return [x.strip() for x in out.stdout.split() if x.strip()]


итог = {'погашено_мост': погасить('zenno_most.py'),
        'погашено_поиск': погасить('poisk_saytov.py')}
time.sleep(5)
итог['сторож'] = S.обход()
time.sleep(20)
живые = S._живые()
итог['крутится_мост'] = bool(S._крутится(живые, 'zenno_most.py', '--demon'))
итог['крутится_поиск'] = bool(S._крутится(живые, 'poisk_saytov.py'))
print(json.dumps(итог, ensure_ascii=False, indent=1))
