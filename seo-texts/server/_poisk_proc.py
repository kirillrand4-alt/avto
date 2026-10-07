# -*- coding: utf-8 -*-
import json, os, subprocess, time, glob, io
DIR = r'C:\sender\server'
cmd = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*poisk_*' -or $_.CommandLine -like '*kc_kontakty*' -or $_.CommandLine -like '*kc_audit*' } | "
       "ForEach-Object { '{0} {1} {2}' -f $_.ProcessId, [math]::Round($_.WorkingSetSize/1MB), $_.CommandLine }")
r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True, timeout=120)
o = {'время': time.strftime('%Y-%m-%d %H:%M:%S'), 'процессы': [x[-120:] for x in r.stdout.splitlines() if x.strip()]}
for ф in glob.glob(os.path.join(DIR, 'poisk*')) + glob.glob(os.path.join(DIR, 'konveyer_poisk*')):
    o[os.path.basename(ф)] = [os.path.getsize(ф), time.strftime('%H:%M', time.localtime(os.path.getmtime(ф)))]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
