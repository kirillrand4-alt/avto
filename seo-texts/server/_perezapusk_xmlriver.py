# -*- coding: utf-8 -*-
r"""Проверить шлюз после пополнения и перезапустить прогон xmlriver."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

DIR = r'C:\sender\server'
o = {}

BASE = (os.environ.get('PROVIDER_BASE_URL') or 'https://router.cheap').rstrip('/')
KEY = os.environ.get('PROVIDER_API_KEY') or ''
H = {'User-Agent': 'curl/8.5.0', 'x-api-key': KEY,
     'anthropic-version': '2023-06-01', 'content-type': 'application/json'}
тело = json.dumps({'model': 'claude-fable-5', 'max_tokens': 24,
                   'messages': [{'role': 'user', 'content': 'Ответь одним словом: готов'}]}).encode()
for попытка in range(3):
    try:
        req = urllib.request.Request(BASE + '/v1/messages', data=тело, headers=H, method='POST')
        with urllib.request.urlopen(req, timeout=60) as r:
            o['шлюз'] = {'код': r.status,
                         'ответ': r.read(300).decode('utf-8', 'replace')[:200]}
        break
    except urllib.error.HTTPError as e:
        o['шлюз'] = {'код': e.code, 'тело': e.read(300).decode('utf-8', 'replace')[:250]}
        break
    except Exception as e:
        o['шлюз'] = {'ошибка': repr(e)[:120], 'попытка': попытка + 1}
        time.sleep(4)

деньги_есть = isinstance(o.get('шлюз'), dict) and o['шлюз'].get('код') == 200
o['баланс_в_порядке'] = деньги_есть

if деньги_есть:
    МЕТКА = time.strftime('%d%m-%H%M')
    ARGS = os.path.join(DIR, 'xmlriver_args_%s.json' % МЕТКА)
    LOG = os.path.join(DIR, 'xmlriver_scan_%s.log' % МЕТКА)
    args = {
        'collectors': ['xmlriver'],
        'xmlriver_engines': ['google', 'yandex'],
        'days': 45,
        'max_items': 8,
        'enrich': True,
        'enrich_max': 0,
        'icp_only': False,
        'write_db': True,
        'provider_workers': 12,
    }
    with open(ARGS, 'w', encoding='utf-8') as f:
        json.dump(args, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    python = r'C:\Program Files\Python312\python.exe'
    if not os.path.exists(python):
        python = sys.executable
    вход = open(ARGS, 'rb')
    выход = open(LOG, 'wb')
    p = subprocess.Popen([python, '-u', 'news_scan.py'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=вход, stdout=выход,
                         stderr=subprocess.STDOUT, close_fds=False)
    вход.close()
    выход.close()
    o['запущен_pid'] = p.pid
    o['лог'] = os.path.basename(LOG)
    time.sleep(70)
    пр = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "$pr = Get-Process -Id %d -ErrorAction SilentlyContinue; "
         "if ($pr) { [math]::Round($pr.CPU,1) } else { 'завершился' }" % p.pid],
        capture_output=True, text=True, timeout=90)
    o['cpu_через_70с'] = (пр.stdout or '').strip()
    if os.path.exists(LOG):
        with open(LOG, encoding='utf-8', errors='replace') as f:
            хвост = f.read()[-400:]
        o['лог_хвост'] = хвост
        o['лог_байт'] = os.path.getsize(LOG)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
