# -*- coding: utf-8 -*-
"""Остановить ТОЛЬКО ca_okved_dobor (PID из замка, проверка командной строки), снять замок — для перезапуска на
свежем лимите DaData (00:12 МСК)."""
import os, subprocess, time
З = r'C:\sender\server\ca\ca_okved_dobor.lock'
print('===ИТОГ===')
pid = open(З).read().strip() if os.path.exists(З) else ''
cmd = subprocess.run(['powershell', '-NoProfile', '-Command',
                      "(Get-CimInstance Win32_Process -Filter 'ProcessId=%s').CommandLine" % (pid or '0')],
                     capture_output=True, text=True, timeout=60).stdout.strip()
print('pid', pid, 'cmd', cmd[-120:])
if pid and 'ca_okved_dobor' in cmd:
    r = subprocess.run(['taskkill', '/PID', pid, '/T', '/F'], capture_output=True, text=True)
    print('taskkill', r.returncode, (r.stdout + r.stderr)[-200:])
    time.sleep(3)
    try:
        os.remove(З)
        print('замок снят')
    except OSError as e:
        print('замок', e)
else:
    print('не трогаю: замка нет или PID не добора')
