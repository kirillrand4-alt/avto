# -*- coding: utf-8 -*-
"""Проба 1: доступен ли egrz.gov.ru с сервера владельца и что он отдаёт.

Только чтение сети и печать. Ничего не пишет в базы.
ВАЖНО: stdout раннера режется СВЕРХУ → главное печатаем ПОСЛЕДНИМ.
"""
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
# в обход системного SOCKS сервера (он режет многие хосты) + неверифицирующий TLS
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))

LOG = []


def get(url, timeout=25, headers=None, data=None, method=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h, data=data, method=method)
        r = _OP.open(req, timeout=timeout)
        body = r.read()
        return r.getcode(), dict(r.headers), body
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:  # noqa: BLE001
            body = b''
        return e.code, dict(e.headers or {}), body
    except Exception as e:  # noqa: BLE001
        return -1, {'err': '%s: %s' % (type(e).__name__, e)}, b''


def probe(name, url, **kw):
    code, hdr, body = get(url, **kw)
    ct = hdr.get('Content-Type', hdr.get('content-type', ''))
    LOG.append((name, url, code, ct, len(body), body[:300]))
    print('[%s] %s -> %s ct=%s len=%d' % (name, url, code, ct, len(body)))
    return code, hdr, body


# 1. главная
code, hdr, body = probe('main', 'https://egrz.gov.ru/')
html = body.decode('utf-8', 'replace')
scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
links = re.findall(r'<link[^>]+href="([^"]+)"', html)
title = re.search(r'<title[^>]*>(.*?)</title>', html, re.S)
print('TITLE:', (title.group(1).strip() if title else '')[:200])
print('SCRIPTS:', scripts[:15])
print('HTML_HEAD_SNIPPET:', html[:600].replace('\n', ' '))

# 2. типовые точки публичного реестра / API (гадаем по практике gov-SPA)
CAND = [
    'https://egrz.gov.ru/organisation/reestr/eer-list',
    'https://egrz.gov.ru/reestr',
    'https://egrz.gov.ru/api/public/reestr',
    'https://egrz.gov.ru/api/Public/Reestr',
    'https://egrz.gov.ru/api/reestr',
    'https://egrz.gov.ru/swagger/index.html',
    'https://egrz.gov.ru/robots.txt',
    'https://egrz.gov.ru/sitemap.xml',
    'https://egrz.gov.ru/opendata',
    'https://egrz.gov.ru/api/config',
]
for u in CAND:
    probe('cand', u, timeout=20)

# 3. главный JS-бандл — ищем в нём пути /api/
api_paths = set()
for s in scripts[:6]:
    u = s if s.startswith('http') else 'https://egrz.gov.ru' + ('' if s.startswith('/') else '/') + s
    c, h, b = get(u, timeout=30)
    print('[js] %s -> %s len=%d' % (u, c, len(b)))
    if c == 200 and b:
        t = b.decode('utf-8', 'replace')
        for m in re.findall(r'["\'`](/?api/[A-Za-z0-9_\-/\.{}\$]{2,80})["\'`]', t):
            api_paths.add(m)

print()
print('==================== ИТОГ (самое важное) ====================')
print('доступность главной: код=%s, длина=%d' % (code, len(body)))
print('найдено api-путей в бандлах: %d' % len(api_paths))
for p in sorted(api_paths)[:60]:
    print('  API:', p)
print('--- таблица проб ---')
for name, url, c, ct, ln, head in LOG:
    print('%-6s %-55s code=%-5s ct=%-30s len=%-8d head=%s'
          % (name, url[:55], c, str(ct)[:30], ln, head[:120]))
