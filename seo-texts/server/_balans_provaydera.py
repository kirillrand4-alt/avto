# -*- coding: utf-8 -*-
"""Баланс провайдерского шлюза и сколько событий успели классифицировать."""
import io, json, os, ssl, urllib.error, urllib.request

o = {}
BASE = (os.environ.get('PROVIDER_BASE_URL') or 'https://router.cheap').rstrip('/')
KEY = os.environ.get('PROVIDER_API_KEY') or ''
H = {'User-Agent': 'curl/8.5.0', 'x-api-key': KEY,
     'anthropic-version': '2023-06-01', 'content-type': 'application/json'}
тело = json.dumps({'model': 'claude-fable-5', 'max_tokens': 16,
                   'messages': [{'role': 'user', 'content': 'ок'}]}).encode()
try:
    req = urllib.request.Request(BASE + '/v1/messages', data=тело, headers=H, method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        o['вызов'] = {'код': r.status, 'тело': r.read(200).decode('utf-8', 'replace')[:150]}
except urllib.error.HTTPError as e:
    o['вызов'] = {'код': e.code, 'тело': e.read(300).decode('utf-8', 'replace')[:280]}
except Exception as e:
    o['вызов'] = repr(e)[:150]

# Сколько сегодняшних событий xmlriver дошли до классификации.
клас = сырых = 0
примеры = []
with io.open(r'C:\sender\server\news_stream.jsonl', encoding='utf-8', errors='replace') as f:
    n = 0
    for s in f:
        n += 1
        if n <= 5270 or 'xmlriver' not in s[:400]:
            continue
        try:
            d = json.loads(s)
        except Exception:
            continue
        if (d.get('event_type') or '').strip():
            клас += 1
            if len(примеры) < 5:
                примеры.append({'кто': str(d.get('company'))[:38], 'инн': d.get('inn'),
                                'что': str(d.get('what'))[:60]})
        else:
            сырых += 1
o['xmlriver_сегодня'] = {'классифицировано': клас, 'без_классификации': сырых,
                         'примеры': примеры}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
