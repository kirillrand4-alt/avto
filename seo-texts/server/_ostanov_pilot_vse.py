# Остановить конвейер пилота и его шаги (по командной строке; этот скрипт под фильтр не попадает)
import json, subprocess
ц = ['server\\pilot_konveyer.py', 'server\\pilot_poisk.py', 'server\\poisk_razbor.py', 'server\\pilot_otbor.py']
усл = ' -or '.join("$_.CommandLine -like '*%s*'" % x for x in ц)
r = subprocess.run(['powershell', '-NoProfile', '-Command',
    "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and (%s) } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }" % усл], capture_output=True, text=True, timeout=60)
print('===ИТОГ==='); print(json.dumps({'остановлены': r.stdout.split(), 'ошибки': r.stderr[-300:]}, ensure_ascii=False))
