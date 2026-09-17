# -*- coding: utf-8 -*-
"""Почему провайдер молчит: жив ли прогон, что в логе, отвечает ли шлюз."""
import io, json, os, ssl, subprocess, time, urllib.error, urllib.request

DIR = r'C:\sender\server'
o = {'сейчас': time.strftime('%H:%M:%S')}

r = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'} | ForEach-Object { "
     "$pr = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; "
     "[pscustomobject]@{pid=$_.ProcessId; cpu=[math]::Round($pr.CPU,0); "
     "mb=[math]::Round($pr.WorkingSet64/1MB,0); start=$_.CreationDate} } | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o['процессы'] = (r.stdout or '').strip()[:400]

логи = sorted([p for p in os.listdir(DIR) if p.startswith('xmlriver_scan_')])
if логи:
    п = os.path.join(DIR, логи[-1])
    st = os.stat(п)
    o['лог'] = {'файл': логи[-1], 'байт': st.st_size,
                'изменён': time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}
    if st.st_size:
        with open(п, encoding='utf-8', errors='replace') as f:
            o['лог']['хвост'] = f.read()[-500:]

П = os.path.join(DIR, 'news_stream.jsonl')
o['поток'] = {'байт': os.path.getsize(П),
              'изменён': time.strftime('%H:%M:%S', time.localtime(os.stat(П).st_mtime))}

# Живой вызов шлюза без стрима.
BASE = (os.environ.get('PROVIDER_BASE_URL') or 'https://router.cheap').rstrip('/')
KEY = os.environ.get('PROVIDER_API_KEY') or ''
H = {'User-Agent': 'curl/8.5.0', 'x-api-key': KEY,
     'anthropic-version': '2023-06-01', 'content-type': 'application/json'}
тело = json.dumps({'model': 'claude-fable-5', 'max_tokens': 16,
                   'messages': [{'role': 'user', 'content': 'ок'}]}).encode()
for i in range(2):
    try:
        t0 = time.time()
        req = urllib.request.Request(BASE + '/v1/messages', data=тело, headers=H, method='POST')
        with urllib.request.urlopen(req, timeout=50) as rr:
            o['шлюз'] = {'код': rr.status, 'сек': round(time.time() - t0, 1),
                         'ответ': rr.read(160).decode('utf-8', 'replace')[:140]}
        break
    except urllib.error.HTTPError as e:
        o['шлюз'] = {'код': e.code, 'тело': e.read(250).decode('utf-8', 'replace')[:230]}
        break
    except Exception as e:
        o['шлюз'] = {'ошибка': repr(e)[:110], 'попытка': i + 1}
        time.sleep(3)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
