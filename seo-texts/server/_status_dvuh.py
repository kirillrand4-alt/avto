import glob, io, json, os, subprocess
DIR = r'C:\sender\server'
o = {}
for имя, лог_маска in (('meyer-proverka-ost.jsonl', 'meyer_proverka_ost_*.log'), ('meyer-nalichie.jsonl', 'meyer_nalichie_*.log')):
    п = os.path.join(DIR, имя)
    o[имя] = sum(1 for _ in io.open(п, encoding='utf-8', errors='replace')) if os.path.exists(п) else 'нет файла'
    логи = sorted(glob.glob(os.path.join(DIR, лог_маска)), key=os.path.getmtime)
    if логи:
        o[имя + ' лог'] = io.open(логи[-1], encoding='utf-8', errors='replace').read()[-300:]
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -match 'meyer_nalichie\\.py|meyer_proverka\\.py' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
                   capture_output=True, text=True, timeout=90)
o['процессы'] = (p.stdout or '').strip()[:500] or 'нет'
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
