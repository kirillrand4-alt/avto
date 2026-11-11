# -*- coding: utf-8 -*-
"""Остановить ТОЛЬКО вторую волну набора ca: обёртку ca_konveyer (PID из замка) со всем деревом (pilot_konveyer,
kc_dorazmetka), снять замок. Досыл агентов (ca_agenty_dosyl) не трогаем."""
import os, subprocess, time
З = r'C:\sender\server\ca\ca_konveyer.lock'
print('===ИТОГ===')
pid = open(З).read().strip() if os.path.exists(З) else ''
cmd = subprocess.run(['powershell', '-NoProfile', '-Command', "(Get-CimInstance Win32_Process -Filter 'ProcessId=%s').CommandLine" % (pid or '0')],
                     capture_output=True, text=True, timeout=60).stdout.strip()
print('pid', pid, cmd[-60:])
if pid and 'ca_konveyer' in cmd:
    r = subprocess.run(['taskkill', '/PID', pid, '/T', '/F'], capture_output=True, text=True)
    print((r.stdout + r.stderr)[-400:])
    time.sleep(3)
    os.remove(З)
    print('замок снят')
r = subprocess.run(['powershell', '-NoProfile', '-Command', "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like '*kc_dorazmetka*' -or $_.CommandLine -like '*pilot_konveyer*' } | ForEach-Object { $_.ProcessId }"], capture_output=True, text=True, timeout=60)
print('осталось', r.stdout.split())
