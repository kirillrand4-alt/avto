# -*- coding: utf-8 -*-
"""Проба 11: единый реестр получателей поддержки (rmsp-pp.nalog.ru) — есть ли API/опендата,
видно ли там ФРП. Только чтение."""
import re
import ssl
import sys
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))


def get(url, timeout=25, headers=None, data=None, method=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    try:
        r = _OP.open(urllib.request.Request(url, headers=h, data=data, method=method), timeout=timeout)
        return r.status, dict(r.headers), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, dict(e.headers), e.read().decode('utf-8', 'replace')
        except Exception:                                    # noqa: BLE001
            return e.code, dict(e.headers), ''
    except Exception as e:                                   # noqa: BLE001
        return -1, {'err': str(e)[:140]}, ''


def plain(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).strip()


rep = []

# 1) главная: ищем JS-бандл и эндпоинты
c, hd, h = get('https://rmsp-pp.nalog.ru/')
rep.append(f'главная {c} {len(h)}')
rep.append('  текст: ' + plain(h)[:700])
srcs = re.findall(r'<script[^>]+src="([^"]+)"', h)
rep.append('  скрипты: ' + str(srcs[:15]))
eps = sorted({x for x in re.findall(r'["\']([a-zA-Z0-9_\-/\.]*\.json[^"\']{0,40})["\']', h)})
rep.append('  json в html: ' + str(eps[:15]))

# 2) опендата
c, hd, h2 = get('https://rmsp-pp.nalog.ru/open-data.html')
rep.append(f'--- open-data {c} {len(h2)}')
rep.append('  текст: ' + plain(h2)[:900])
for href in sorted({x for x in re.findall(r'href="([^"]+)"', h2) if not x.startswith('#')})[:25]:
    rep.append('   ссылка: ' + href[:120])

# 3) JS-бандл → эндпоинты API
for s in srcs:
    if not s.endswith('.js'):
        continue
    u = urllib.parse.urljoin('https://rmsp-pp.nalog.ru/', s)
    c3, hd3, js = get(u)
    found = sorted({x for x in re.findall(r'["\']([a-zA-Z0-9_\-/\.]{4,60}\.json)["\']', js)})
    found += sorted({x for x in re.findall(r'["\'](/[a-zA-Z0-9_\-/]{3,50}\?[^"\']{0,40})["\']', js)})
    if found:
        rep.append(f'   {u} ({c3}, {len(js)}b) -> {found[:20]}')

# 4) статистика (сколько записей)
c, hd, h4 = get('https://rmsp-pp.nalog.ru/statistics.html')
rep.append(f'--- statistics {c} {len(h4)}')
rep.append('  текст: ' + plain(h4)[:1200])

print('\n'.join(rep[-120:]))
sys.stdout.flush()
