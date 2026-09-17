# -*- coding: utf-8 -*-
"""Как идёт прогон xmlriver: процесс, лог, поток, баланс."""
import glob, io, json, os, subprocess, time, urllib.request

DIR = r'C:\sender\server'
time.sleep(150)
o = {'сейчас': time.strftime('%H:%M:%S')}
r = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'} | ForEach-Object { "
     "$pr = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; "
     "[pscustomobject]@{pid=$_.ProcessId; cpu=[math]::Round($pr.CPU,0); "
     "mb=[math]::Round($pr.WorkingSet64/1MB,0)} } | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o['процессы'] = (r.stdout or '').strip()[:250]

for п in sorted(glob.glob(os.path.join(DIR, 'xmlriver_scan_*.log')), key=os.path.getmtime)[-1:]:
    st = os.stat(п)
    o['лог'] = {'файл': os.path.basename(п), 'байт': st.st_size,
                'изменён': time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}
    if st.st_size:
        with open(п, encoding='utf-8', errors='replace') as f:
            o['лог']['хвост'] = f.read()[-700:]

П = os.path.join(DIR, 'news_stream.jsonl')
o['поток_байт'] = os.path.getsize(П)
n = xm = 0
with io.open(П, encoding='utf-8', errors='replace') as f:
    for s in f:
        n += 1
        if n > 5270 and 'xmlriver' in s[:400]:
            xm += 1
o['строк_в_потоке'] = n
o['новых_от_xmlriver'] = xm

U = os.environ.get('XMLRIVER_USER', ''); K = os.environ.get('XMLRIVER_KEY', '')
try:
    with urllib.request.urlopen(
            'http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (U, K), timeout=30) as r2:
        o['баланс'] = r2.read(100).decode('utf-8', 'replace').strip()
except Exception as e:
    o['баланс'] = repr(e)[:60]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
