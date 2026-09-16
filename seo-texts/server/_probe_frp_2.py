# -*- coding: utf-8 -*-
"""Проба 2: sitemap + поиск XHR-ручки карты/реестра проектов ФРП. Только чтение."""
import gzip
import io
import re
import ssl
import sys
import urllib.request
from collections import Counter

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))


def get(url, timeout=30, headers=None, data=None, method=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h, data=data, method=method)
        r = _OP.open(req, timeout=timeout)
        b = r.read()
        if (r.headers.get('Content-Encoding') or '') == 'gzip' or url.endswith('.gz'):
            try:
                b = gzip.GzipFile(fileobj=io.BytesIO(b)).read()
            except Exception:                                # noqa: BLE001
                pass
        return r.status, b
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:                                    # noqa: BLE001
            return e.code, b''
    except Exception as e:                                   # noqa: BLE001
        return -1, str(e)[:160].encode()


rep = []

# 1) sitemap
code, b = get('https://frprf.ru/sitemap.xml')
txt = b.decode('utf-8', 'replace')
subs = re.findall(r'<loc>([^<]+)</loc>', txt)
rep.append(f'sitemap.xml -> {code}, локаций {len(subs)}')
for s in subs[:20]:
    rep.append('   ' + s)

# разбор вложенных карт (если это индекс)
urls = []
if subs and all(s.endswith('.xml') for s in subs[:3]):
    for s in subs[:12]:
        c2, b2 = get(s)
        u2 = re.findall(r'<loc>([^<]+)</loc>', b2.decode('utf-8', 'replace'))
        rep.append(f'   {s} -> {c2}, url {len(u2)}')
        urls += u2
else:
    urls = subs
seg = Counter(re.sub(r'^https?://frprf\.ru/([^/]*)/?.*$', r'\1', u) for u in urls)
rep.append('разделы sitemap (top-25): ' + str(seg.most_common(25)))

# 2) ищем в главной и в /o-fonde/ признаки XHR карты проектов
for page in ('https://frprf.ru/', 'https://frprf.ru/o-fonde/'):
    c, b = get(page)
    h = b.decode('utf-8', 'replace')
    rep.append(f'--- {page} ({c}, {len(h)} симв.)')
    found = set()
    for pat in (r'["\']([^"\']*\.json[^"\']*)["\']',
                r'["\'](/ajax/[^"\']+)["\']',
                r'["\'](/api/[^"\']+)["\']',
                r'["\'](/local/[^"\']+\.php[^"\']*)["\']',
                r'["\'](/bitrix/[^"\']+\.php[^"\']*)["\']',
                r'url\s*:\s*["\']([^"\']+)["\']'):
        for m in re.findall(pat, h):
            if len(m) < 200:
                found.add(m)
    for f in sorted(found)[:40]:
        rep.append('   XHR? ' + f)
    # ссылки, где встречается слово «проект» в тексте ссылки
    for href, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.{0,120}?)</a>', h, re.S):
        tt = re.sub(r'<[^>]+>|\s+', ' ', t).strip()
        if re.search(r'проект|карт[аеу]|реестр|профинанс', tt, re.I) and len(href) < 90:
            rep.append(f'   ССЫЛКА «{tt[:60]}» -> {href}')

print('\n'.join(rep[-220:]))
sys.stdout.flush()
