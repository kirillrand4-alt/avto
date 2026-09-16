# -*- coding: utf-8 -*-
"""Проба 3: раздел /klienty/ — это и есть реестр профинансированных проектов?
Смотрим: список URL из sitemap-iblock-31, страницу-список, карточку проекта. Только чтение."""
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
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:                                    # noqa: BLE001
            return e.code, b''
    except Exception as e:                                   # noqa: BLE001
        return -1, str(e)[:160].encode()


def txt(b):
    return b.decode('utf-8', 'replace')


rep = []

# 1) sitemap клиентов
c, b = get('https://frprf.ru/sitemap-iblock-31.xml')
u31 = re.findall(r'<loc>([^<]+)</loc>', txt(b))
lm = re.findall(r'<lastmod>([^<]+)</lastmod>', txt(b))
rep.append(f'sitemap-iblock-31 -> {c}, URL {len(u31)}')
rep.append('  сегменты: ' + str(Counter(re.sub(r'^https?://frprf\.ru/([^/]*)/?.*$', r'\1', u)
                                        for u in u31).most_common(5)))
rep.append('  примеры: ' + ' | '.join(u31[:5]))
rep.append('  lastmod свежие: ' + ' '.join(sorted(lm)[-5:]) if lm else '  lastmod нет')

# 2) страница-список
for u in ('https://frprf.ru/klienty/', 'https://frprf.ru/klienty/?PAGEN_1=2'):
    c, b = get(u)
    h = txt(b)
    ttl = re.search(r'<title[^>]*>(.*?)</title>', h, re.S)
    rep.append(f'--- {u} -> {c}, {len(h)} симв., title='
               + (re.sub(r'\s+', ' ', ttl.group(1)).strip()[:60] if ttl else ''))
    links = sorted(set(re.findall(r'href="(/klienty/[^"?#]+/)"', h)))
    rep.append(f'   карточек на странице: {len(links)}; первые: ' + ' | '.join(links[:5]))
    # пагинация/счётчик
    for m in re.findall(r'PAGEN_1=(\d+)', h):
        pass
    pg = sorted({int(x) for x in re.findall(r'PAGEN_1=(\d+)', h)})
    rep.append(f'   PAGEN_1 на странице: {pg[:12]}{" ... max=" + str(pg[-1]) if pg else ""}')
    for pat in (r'["\'](/ajax/[^"\']+)["\']', r'["\'](/api/[^"\']+)["\']',
                r'["\'](/local/[^"\']+\.php[^"\']*)["\']', r'url\s*:\s*["\']([^"\']+)["\']',
                r'["\']([^"\']*\.json[^"\']*)["\']'):
        for x in set(re.findall(pat, h)):
            if len(x) < 160:
                rep.append('   XHR? ' + x)
    # поля фильтра
    for nm in sorted(set(re.findall(r'name="([^"]{2,40})"', h)))[:30]:
        rep.append('   input name=' + nm)

# 3) карточка
if u31:
    card = [u for u in u31 if '/klienty/' in u][:1]
    for u in card:
        c, b = get(u)
        h = txt(b)
        plain = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
        rep.append(f'--- КАРТОЧКА {u} -> {c}, {len(h)} симв.')
        rep.append('   текст[0:1800]: ' + plain[:1800])

print('\n'.join(rep[-200:]))
sys.stdout.flush()
