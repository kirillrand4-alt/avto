import subprocess, os, glob, time
print('===ИТОГ===')
r = subprocess.run(['powershell', '-NoProfile', '-Command', "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*agenty_ab*' } | Select-Object ProcessId,CreationDate,KernelModeTime,UserModeTime | Format-Table -AutoSize | Out-String -Width 200"], capture_output=True, text=True, timeout=120)
print(r.stdout[-1500:])
for п in glob.glob(r'C:\sender\server\pilot_ab_*.log'):
    print(п, time.ctime(os.path.getmtime(п)), os.path.getsize(п))
print(time.ctime())
