# -*- coding: utf-8 -*-
"""Открыты ли остальные двери ЕГРЗ: lk.egrz.ru/OPENAPI, FWS, SRCWS, dv-api, reestr."""
import json
import ssl
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://egrz.ru/',
     'Accept': 'application/json,text/html,*/*'}
o = {}

адреса = [
    'https://lk.egrz.ru/OPENAPI/',
    'https://lk.egrz.ru/OPENAPI/swagger/index.html',
    'https://lk.egrz.ru/OPENAPI/swagger/v1/swagger.json',
    'https://lk.egrz.ru/FWS/',
    'https://lk.egrz.ru/SRCWS/',
    'https://lk.egrz.ru/',
    'http://dv-api.egrz.ru/',
    'http://reestr.egrz.ru/EGRZ/',
    'https://open-api.egrz.ru/api/Analytics?$top=1',
    'https://open-api.egrz.ru/api/Statistic?$top=3',
]

for u in адреса:
    try:
        req = urllib.request.Request(u, headers=H)
        with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
            тело = r.read(400)
            o[u] = {'код': r.status, 'тип': r.headers.get('Content-Type', '')[:40],
                    'начало': тело.decode('utf-8', 'replace').replace('\n', ' ')[:160]}
    except urllib.error.HTTPError as e:
        o[u] = {'код': e.code,
                'тело': e.read(160).decode('utf-8', 'replace').replace('\n', ' ')[:160]}
    except Exception as e:
        o[u] = {'ошибка': repr(e)[:110]}

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
