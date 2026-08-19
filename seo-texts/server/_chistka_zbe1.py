# -*- coding: utf-8 -*-
"""Убрать осиротевшие браузеры Зенки: задача стоит на 0 потоков, а они висят."""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
# сверяем: есть ли работающая задача (иначе zbe1 — сироты)
try:
    d = json.load(open(r'C:\seostat\drop\zenno\dispetcher.json', encoding='utf-8-sig'))
    занято = sum(int(z.get('potokov_seychas') or 0) for z in (d.get('zadachi') or []))
    итог['потоков_занято_по_диспетчеру'] = занято
except Exception as e:  # noqa: BLE001
    итог['диспетчер'] = str(e)[:80]
    занято = None
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "(Get-Process zbe1 -ErrorAction SilentlyContinue | Measure-Object "
                    "WorkingSet -Sum).Sum/1MB; (Get-Process zbe1 -ErrorAction "
                    "SilentlyContinue).Count"],
                   capture_output=True, text=True, timeout=180)
числа = [x.strip() for x in (p.stdout or '').split() if x.strip()]
итог['zbe1_до'] = числа
if '--ubrat' in sys.argv and занято in (0, 1):
    k = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-Process zbe1 -ErrorAction SilentlyContinue | "
                        "Stop-Process -Force; Start-Sleep 3; "
                        "(Get-Process zbe1 -ErrorAction SilentlyContinue).Count"],
                       capture_output=True, text=True, timeout=300)
    итог['осталось_zbe1'] = (k.stdout or '').strip()[:20]
    итог['убрано'] = True
elif '--ubrat' in sys.argv:
    итог['не_трогаем'] = 'диспетчер показывает занятые потоки — это не сироты'
m = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "$os=Get-CimInstance Win32_OperatingSystem; "
                    "[math]::Round($os.FreePhysicalMemory/1MB,1)"],
                   capture_output=True, text=True, timeout=120)
итог['свободно_ГБ'] = (m.stdout or '').strip()
print(json.dumps(итог, ensure_ascii=False, indent=1))
