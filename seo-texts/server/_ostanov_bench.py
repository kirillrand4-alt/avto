# Остановить сравнение моделей (фильтр по server\pilot_bench_modeli.py; этот скрипт под фильтр не попадает)
import json, subprocess
r = subprocess.run(['powershell', '-NoProfile', '-Command',
    "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*server\\pilot_bench_modeli.py*' } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"], capture_output=True, text=True, timeout=60)
print('===ИТОГ==='); print(json.dumps({'остановлены': r.stdout.split(), 'ошибки': r.stderr[-300:]}, ensure_ascii=False))
