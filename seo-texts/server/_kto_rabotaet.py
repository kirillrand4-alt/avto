import subprocess
r = subprocess.run(['powershell', '-NoProfile', '-Command',
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } | Select-Object ProcessId,CreationDate,CommandLine | Format-Table -AutoSize -Wrap | Out-String -Width 260"],
  capture_output=True, text=True, timeout=120)
print('===ИТОГ==='); print(r.stdout[-4000:])
