import json, subprocess
cmd = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and ($_.CommandLine -like '*\\poisk_konveyer.py*' -or $_.CommandLine -like '*\\poisk_otbor.py*') } | "
       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }")
r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True, timeout=120)
print('===ИТОГ==='); print(json.dumps({'стоп': r.stdout.split()}))
