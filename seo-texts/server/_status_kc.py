import glob, io, json, os, shutil, subprocess
DIR = r'C:\sender\server'
o = {'свободно_C_ГБ': round(shutil.disk_usage('C:\\').free / 1e9, 1)}
for маска in ('kc_raspakovka_*.log', 'cc_checko_proxy_*.log'):
    логи = sorted(glob.glob(os.path.join(DIR, маска)), key=os.path.getmtime)
    if логи:
        o[маска] = [os.path.basename(логи[-1]), io.open(логи[-1], encoding='utf-8', errors='replace').read()[-400:]]
п = os.path.join(DIR, 'kc-raspakovka.json')
o['итог_распаковки'] = json.load(io.open(п, encoding='utf-8')) if os.path.exists(п) else 'ещё нет'
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -match 'kc_raspakovka\\.py|cc_checko_proxy\\.py' } | Select-Object ProcessId,@{n='c';e={$_.CommandLine.Substring([Math]::Max(0,$_.CommandLine.Length-40))}} | ConvertTo-Json -Compress"],
                   capture_output=True, text=True, timeout=90)
o['процессы'] = (p.stdout or '').strip()[:400] or 'нет'
if os.path.isdir(r'C:\seostat\kc-proekty'):
    n = 0
    for _, _, ff in os.walk(r'C:\seostat\kc-proekty'):
        n += len(ff)
    o['файлов_распаковано_сейчас'] = n
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:4000])
