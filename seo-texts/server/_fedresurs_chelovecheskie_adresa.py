# -*- coding: utf-8 -*-
"""Человеческие адреса Федресурса: что открывается в браузере и с какими фильтрами."""
import json
import ssl
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
     'Referer': 'https://fedresurs.ru/', 'Accept': 'application/json,text/html,*/*'}
o = {}

адреса = [
    'https://fedresurs.ru/encumbrances',
    'https://fedresurs.ru/sfactmessages',
    'https://fedresurs.ru/search/entity',
    'https://fedresurs.ru/backend/encumbrances?limit=5&offset=0',
    'https://fedresurs.ru/backend/sfactmessages?limit=5',
    'https://fedresurs.ru/backend/encumbrances/types',
    'https://fedresurs.ru/robots.txt',
]

for u in адреса:
    try:
        req = urllib.request.Request(u, headers=H)
        with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
            тело = r.read(600)
            o[u] = {'код': r.status, 'тип': r.headers.get('Content-Type', '')[:40],
                    'начало': тело.decode('utf-8', 'replace').replace('\n', ' ')[:250]}
    except urllib.error.HTTPError as e:
        o[u] = {'код': e.code,
                'тело': e.read(200).decode('utf-8', 'replace').replace('\n', ' ')[:200]}
    except Exception as e:
        o[u] = {'ошибка': repr(e)[:110]}

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
