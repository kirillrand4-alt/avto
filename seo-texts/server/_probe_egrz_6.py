# -*- coding: utf-8 -*-
"""Проба 6: open-api.egrz.ru — публичная книга регистрации заключений.
Смотрим коды, формат ответа, имена полей + как фронт строит OData-запрос.
Только чтение и печать. Главное — ПОСЛЕДНИМ."""
import re
import ssl
import json
import urllib.request
import urllib.error

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
API = 'https://open-api.egrz.ru/'


def get(url, timeout=45, headers=None):
    h = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
         'Accept-Language': 'ru,en;q=0.9', 'Origin': 'https://egrz.ru',
         'Referer': 'https://egrz.ru/'}
    if headers:
        h.update(headers)
    try:
        r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.getcode(), dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), (e.read() if e.fp else b'')
    except Exception as e:  # noqa: BLE001
        return -1, {}, ('ERR %s: %s' % (type(e).__name__, e)).encode()


RES = []
SAMPLE = ''
URLS = [
    API + 'api/PublicRegistrationBook?$top=1&$count=true',
    API + 'api/PublicRegistrationBook?%24top=1&%24count=true',
    API + 'api/PublicRegistrationBook',
    API + 'api/dictionary/subjectRfes?withIntCode=true',
    API + 'api/Kosfn',
    API + 'swagger/index.html',
    API + 'swagger/v1/swagger.json',
]
for u in URLS:
    c, h, b = get(u)
    ct = str(h.get('Content-Type', h.get('content-type', '')))[:30]
    RES.append((u.replace(API, '/')[:70], c, ct, len(b), b[:200]))
    print(u[:110], '->', c, len(b))
    if c == 200 and 'json' in ct and 'PublicRegistrationBook' in u and not SAMPLE:
        SAMPLE = b.decode('utf-8', 'replace')

# как фронт зовёт книгу: ищем в бандле $filter / $top / имена полей
c, b = 0, b''
try:
    r = _OP.open(urllib.request.Request('https://egrz.ru/main.bundle.js',
                                        headers={'User-Agent': UA}), timeout=60)
    big = r.read().decode('utf-8', 'replace')
except Exception:  # noqa: BLE001
    big = ''
ctx = []
if big:
    for pat in (r'.{80}\$filter.{160}', r'.{60}publicRegistrationBook.{200}',
                r'.{40}\$orderby.{120}'):
        for m in list(re.finditer(pat, big))[:6]:
            ctx.append(m.group(0))

print()
print('==================== ИТОГ ====================')
for u, c, ct, ln, head in RES:
    print('%-70s code=%-5s ct=%-22s len=%-8d head=%s'
          % (u, c, ct, ln, head[:110].decode('utf-8', 'replace').replace('\n', ' ')))
print()
print('--- контексты из бандла ---')
for s in ctx[:14]:
    print('  ', s.replace('\n', ' ')[:250])
print()
print('--- ОБРАЗЕЦ ОТВЕТА КНИГИ (первые 2500 символов) ---')
print(SAMPLE[:2500] if SAMPLE else '(json не получен)')
