# -*- coding: utf-8 -*-
"""Проба 1: разведка сайта ФРП с РОССИЙСКОГО сервера.

Задача: найти реестр профинансированных проектов (займов) и его XHR/JSON-ручку.
Только чтение сети + печать. Ничего не пишем.
ВАЖНО: stdout раннера режется СВЕРХУ → главное печатаем ПОСЛЕДНИМ.
"""
import re
import ssl
import sys
import time
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
# системный SOCKS-прокси сервера режет часть хостов → идём в обход (как _NOPROXY в news_scan)
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))


def get(url, timeout=25, headers=None, data=None, method=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h, data=data, method=method)
        r = _OP.open(req, timeout=timeout)
        body = r.read()
        return r.status, dict(r.headers), body
    except urllib.error.HTTPError as e:                      # noqa: PERF203
        try:
            body = e.read()
        except Exception:                                    # noqa: BLE001
            body = b''
        return e.code, dict(e.headers), body
    except Exception as e:                                   # noqa: BLE001
        return -1, {'err': str(e)[:160]}, b''


def brief(url, **kw):
    t0 = time.time()
    code, hdr, body = get(url, **kw)
    ct = (hdr.get('Content-Type') or hdr.get('content-type') or hdr.get('err') or '')[:60]
    return code, len(body), ct, round(time.time() - t0, 1), body


rep = []

# 1) robots.txt + sitemap
code, n, ct, t, body = brief('https://frprf.ru/robots.txt')
rep.append(f'robots.txt -> {code} {n}b {ct} {t}s')
sitemaps = re.findall(r'(?im)^\s*sitemap:\s*(\S+)', body.decode('utf-8', 'replace'))
rep.append('  sitemap: ' + (', '.join(sitemaps[:5]) or 'нет'))

# 2) главная — собираем ссылки-кандидаты
code, n, ct, t, body = brief('https://frprf.ru/')
rep.append(f'главная -> {code} {n}b {ct} {t}s')
home = body.decode('utf-8', 'replace')
hrefs = set(re.findall(r'href="([^"]+)"', home))
cand = sorted(h for h in hrefs
              if re.search(r'proekt|zaym|zaim|karta|reestr|profinans|map', h, re.I))
rep.append('  ссылки-кандидаты (%d):' % len(cand))
for h in cand[:40]:
    rep.append('    ' + h[:120])

# 3) кандидаты путей
PATHS = [
    'https://frprf.ru/proekty/',
    'https://frprf.ru/proekty/karta-proektov/',
    'https://frprf.ru/zaymy/',
    'https://frprf.ru/zaimy/',
    'https://frprf.ru/o-fonde/',
    'https://frprf.ru/press-tsentr/novosti/',
    'https://frprf.ru/map/',
    'https://frprf.ru/karta-proektov/',
]
rep.append('--- пути:')
for u in PATHS:
    code, n, ct, t, b = brief(u)
    ttl = re.search(r'<title[^>]*>(.*?)</title>', b.decode('utf-8', 'replace'), re.S)
    rep.append(f'  {code} {n:>8}b {t:>4}s {ct[:30]:<30} {u}  | '
               + (re.sub(r'\s+', ' ', ttl.group(1)).strip()[:70] if ttl else ''))

print('\n'.join(rep))
sys.stdout.flush()
