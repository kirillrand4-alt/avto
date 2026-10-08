# Остановить pilot_konveyer.py (фильтр по командной строке; сам этот скрипт в фильтр не попадает)
import json, subprocess
r = subprocess.run(['powershell', '-NoProfile', '-Command',
    "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*server\\pilot_konveyer.py*' } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"], capture_output=True, text=True, timeout=60)
print('===ИТОГ==='); print(json.dumps({'остановлены': r.stdout.split(), 'ошибки': r.stderr[-300:]}, ensure_ascii=False))
