import json, os, subprocess, time
DIR = r'C:\sender\server'
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -match 'meyer_nalichie\\.py' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
                   capture_output=True, text=True, timeout=120)
time.sleep(3)
п = os.path.join(DIR, 'meyer-nalichie.jsonl')
стар = п + '.bez-proverki-kompanii-' + time.strftime('%H%M')
n = 0
if os.path.exists(п):
    n = sum(1 for _ in open(п, encoding='utf-8', errors='replace'))
    os.replace(п, стар)
print('===ИТОГ===')
print(json.dumps({'остановлен': (p.stdout or '').split(), 'было_строк': n, 'отложено_в': os.path.basename(стар)}, ensure_ascii=False))
