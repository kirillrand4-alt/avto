# -*- coding: utf-8 -*-
import json, subprocess
cmd = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*kc_konveyer.py*' -or "
       "$_.CommandLine -like '*kc_okved_fns.py*' -or $_.CommandLine -like '*kc_kontakty.py*' -or "
       "$_.CommandLine -like '*kc_sayty.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }")
r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True, timeout=120)
print('===ИТОГ===')
print(json.dumps({'остановлены_pid': r.stdout.split(), 'err': r.stderr[-300:]}, ensure_ascii=False))
