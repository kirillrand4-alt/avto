import glob, io, json, os, subprocess
DIR = r'C:\sender\server'
п = os.path.join(DIR, 'cc-obhod.jsonl')
o = {'сайтов_готово': sum(1 for _ in io.open(п, encoding='utf-8', errors='replace')) if os.path.exists(п) else 'нет файла'}
логи = sorted(glob.glob(os.path.join(DIR, 'cc_obhod_*.log')), key=os.path.getmtime)
if логи:
    o['лог'] = io.open(логи[-1], encoding='utf-8', errors='replace').read()[-400:]
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -match 'cc_obhod\\.py' } | Select-Object -ExpandProperty ProcessId"],
                   capture_output=True, text=True, timeout=90)
o['процесс'] = (p.stdout or '').strip() or 'нет'
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
