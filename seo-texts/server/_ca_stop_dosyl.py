import os, subprocess
З = r'C:\sender\server\ca\ca_agenty_dosyl.lock'
pid = open(З).read().strip() if os.path.exists(З) else ''
cmd = subprocess.run(['powershell', '-NoProfile', '-Command', "(Get-CimInstance Win32_Process -Filter 'ProcessId=%s').CommandLine" % (pid or '0')], capture_output=True, text=True, timeout=60).stdout
print('===ИТОГ=== pid', pid, cmd.strip()[-50:])
if pid and 'ca_agenty_dosyl' in cmd:
    r = subprocess.run(['taskkill', '/PID', pid, '/T', '/F'], capture_output=True, text=True)
    print((r.stdout + r.stderr)[-300:])
    try:
        os.remove(З); print('замок снят')
    except OSError as e:
        print(e)
