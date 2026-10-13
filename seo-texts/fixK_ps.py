import subprocess
r = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*checko_meyer_fixK*' } | ForEach-Object { $_.ProcessId.ToString() + ' ' + $_.CommandLine }"],
                   capture_output=True, text=True, timeout=120)
print(r.stdout[-2000:])
