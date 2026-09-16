# -*- coding: utf-8 -*-
"""Проба 4: вытащить из бандла реальные базовые URL (publicAPI/PublicPortal_API)
и постучаться в api/PublicRegistrationBook (OData?).

Только чтение сети и печать. Главное — последним.
"""
import re
import ssl
import json
import urllib.request
import urllib.error
import urllib.parse

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
BASE = 'https://egrz.ru'


def get(url, timeout=40, headers=None, data=None, method=None):
    h = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
         'Accept-Language': 'ru,en;q=0.9', 'Referer': BASE + '/'}
    if headers:
        h.update(headers)
    try:
        r = _OP.open(urllib.request.Request(url, headers=h, data=data, method=method),
                     timeout=timeout)
        return r.getcode(), dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        try:
            b = e.read()
        except Exception:  # noqa: BLE001
            b = b''
        return e.code, dict(e.headers or {}), b
    except Exception as e:  # noqa: BLE001
        return -1, {}, ('ERR %s: %s' % (type(e).__name__, e)).encode()


# 1. главный бандл
c, h, b = get(BASE + '/')
scripts = re.findall(r'<script[^>]+src="([^"]+)"', b.decode('utf-8', 'replace'))
big = ''
for s in scripts:
    u = s if s.startswith('http') else BASE + '/' + s.lstrip('/')
    cc, hh, bb = get(u, timeout=60)
    if cc == 200 and b'publicAPI' in bb:
        big = bb.decode('utf-8', 'replace')
        print('бандл с конфигом:', s, len(bb))
        break

CONF = []
if big:
    i = big.find('publicAPI=')
    if i > 0:
        CONF.append(('around publicAPI', big[max(0, i - 900):i + 600]))
    for key in ('PublicPortal_API', 'lkAPI=', 'crmAPI=', 'front='):
        j = big.find(key)
        if j > 0:
            CONF.append((key, big[max(0, j - 300):j + 300]))

OUT = []


def probe(url, tag='', headers=None, data=None, method=None):
    c, hd, bb = get(url, headers=headers, data=data, method=method)
    ct = hd.get('Content-Type', hd.get('content-type', ''))
    OUT.append((tag or url, c, str(ct)[:40], len(bb), bb[:500]))
    print('[%s] %s -> %s len=%d' % (tag, url[:120], c, len(bb)))
    return c, hd, bb


# 2. кандидаты публичной ручки реестра
CAND = [
    BASE + '/api/PublicRegistrationBook?$top=2',
    BASE + '/api/PublicRegistrationBook?%24top=2&%24count=true',
    BASE + '/api/PublicRegistrationBook',
    BASE + '/api/dictionary/subjectRfes?withIntCode=true',
    BASE + '/api/Kosfn',
    BASE + '/api/News/',
    BASE + '/api/Statistic',
    BASE + '/api/organizations',
    BASE + '/api/fiasRegions',
]
for u in CAND:
    probe(u, tag='cand')

print()
print('==================== ИТОГ ====================')
for tag, key_ctx in CONF:
    print('### %s ###' % tag)
    print(key_ctx.replace('\n', ' ')[:1400])
    print()
print('--- пробы ---')
for tag, c, ct, ln, head in OUT:
    print('%-6s code=%-5s ct=%-28s len=%-8d head=%s'
          % (tag, c, ct, ln, head[:260].decode('utf-8', 'replace').replace('\n', ' ')))
