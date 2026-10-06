import json, subprocess
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -match 'meyer_proverka_vse\.py' } | Select-Object ProcessId | ConvertTo-Json"],
                   capture_output=True, text=True, timeout=90)
print('===ИТОГ===')
print(json.dumps({'python_со_сверкой': (p.stdout or '').strip() or 'нет'}, ensure_ascii=False))
