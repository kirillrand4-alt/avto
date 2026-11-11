import json, subprocess
o = json.load(open(r'C:\sender\server\ca-konveyer.json', encoding='utf-8'))
print('===ИТОГ===', [(k, v.get('старт'), v.get('конец', 'идёт')) for k, v in list(o.get('шаги', {}).items())[-3:]])
r = subprocess.run(['powershell', '-NoProfile', '-Command', "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like '*kc_agent*' -or $_.CommandLine -like '*glubokiy*' -or $_.CommandLine -like '*dosyl*' } | ForEach-Object { \"$($_.ProcessId) $($_.ParentProcessId) \" + ($_.CommandLine -replace '.*\\\\','') }"], capture_output=True, text=True, timeout=120)
print(r.stdout.strip())
