# -*- coding: utf-8 -*-
"""Проба 3: egrz.ru — SPA, ищем публичные ручки API в JS-бандлах.

Только чтение сети и печать. Главное — последним.
"""
import re
import ssl
import urllib.request
import urllib.error

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
BASE = 'https://egrz.ru'


def get(url, timeout=30, headers=None, data=None, method=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.9',
         'Referer': BASE + '/'}
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


OUT = []

code, hdr, body = get(BASE + '/')
html = body.decode('utf-8', 'replace')
OUT.append(('main', BASE + '/', code, len(body)))
scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
print('scripts:', scripts)

# robots / sitemap / swagger
for p in ('/robots.txt', '/sitemap.xml', '/swagger/index.html', '/swagger/v1/swagger.json',
          '/assets/config.json', '/assets/appsettings.json'):
    c, h, b = get(BASE + p, timeout=20)
    OUT.append(('aux', p, c, len(b)))
    if c == 200 and len(b) < 3000:
        print('--- %s ---' % p, b[:1200].decode('utf-8', 'replace').replace('\n', ' '))

api = set()
JS = []
for s in scripts:
    u = s if s.startswith('http') else BASE + ('' if s.startswith('/') else '/') + s
    c, h, b = get(u, timeout=60)
    OUT.append(('js', s[:50], c, len(b)))
    print('js %s -> %s len=%d' % (s[:60], c, len(b)))
    if c == 200 and b:
        t = b.decode('utf-8', 'replace')
        JS.append(t)
        for m in re.findall(r'["\'`]((?:/|\.\./)?[A-Za-z0-9_\-/]*api/[A-Za-z0-9_\-/\.]{2,90})["\'`]', t):
            api.add(m)

# поищем слова-подсказки в бандле
hints = {}
for w in ('Reestr', 'reestr', 'GetList', 'Search', 'Conclusion', 'zakluch', 'EEList',
          'PublicReestr', 'gridSearch', 'odata'):
    n = sum(t.count(w) for t in JS)
    if n:
        hints[w] = n

# куски вокруг 'api/' — чтобы увидеть, как строится URL
ctx = []
for t in JS:
    for m in re.finditer(r'.{60}api/[A-Za-z0-9_\-/]{2,60}.{40}', t):
        ctx.append(m.group(0))
        if len(ctx) > 40:
            break
    if len(ctx) > 40:
        break

print()
print('==================== ИТОГ ====================')
for tag, what, c, ln in OUT:
    print('%-5s %-60s code=%-5s len=%d' % (tag, str(what)[:60], c, ln))
print('hints:', hints)
print('--- api-пути (%d) ---' % len(api))
for p in sorted(api)[:70]:
    print('   ', p)
print('--- контексты api/ ---')
for s in ctx[:25]:
    print('   ', s.replace('\n', ' ')[:180])
