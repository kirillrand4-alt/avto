import json, subprocess
o = json.load(open(r'C:\sender\server\ca-konveyer.json', encoding='utf-8'))
print('===ИТОГ===', [(k, v.get('старт'), v.get('конец', 'идёт')) for k, v in list(o.get('шаги', {}).items())[-3:]])
r = subprocess.run(['powershell', '-NoProfile', '-Command', "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like '*kc_*' -or $_.CommandLine -like '*pilot_*' -or $_.CommandLine -like '*ca_*' } | ForEach-Object { \"$($_.ProcessId) \" + ($_.CommandLine -replace '.*\\\\','') }"], capture_output=True, text=True, timeout=120)
print(r.stdout.strip())
