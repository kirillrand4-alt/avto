import subprocess
r = subprocess.run(['powershell', '-NoProfile', '-Command',
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*server\\pilot_agenty_ab.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
  capture_output=True, text=True, timeout=120)
print('===ИТОГ==='); print('остановлены:', r.stdout.split(), r.stderr[-300:])
