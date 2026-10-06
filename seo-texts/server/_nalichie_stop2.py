import json, subprocess
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -match 'meyer_nalichie\\.py' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
                   capture_output=True, text=True, timeout=120)
print('===ИТОГ===')
print(json.dumps({'остановлен': (p.stdout or '').split()}, ensure_ascii=False))
