# -*- coding: utf-8 -*-
"""Проба 6: /klienty/?region= — редирект или реестр? + статистика заявок + region_js на главной."""
import re
import ssl
import sys
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
_NOR = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                   urllib.request.HTTPSHandler(context=_CTX), NoRedirect)


def get(url, op=None, timeout=30, headers=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    op = op or _OP
    try:
        r = op.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, dict(e.headers), e.read()
        except Exception:                                    # noqa: BLE001
            return e.code, dict(e.headers), b''
    except Exception as e:                                   # noqa: BLE001
        return -1, {'err': str(e)[:150]}, b''


def plain(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).strip()


rep = []

# 1) редиректы
for u in ('https://frprf.ru/klienty/', 'https://frprf.ru/klienty/?region=77',
          'https://frprf.ru/klienty/42484/'):
    c, hd, b = get(u, op=_NOR)
    rep.append(f'БЕЗ РЕДИРЕКТА {u} -> {c} loc={hd.get("Location", "-")} len={len(b)}')

# 2) region-фильтр
for u in ('https://frprf.ru/klienty/?region=77', 'https://frprf.ru/klienty/?region=66',
          'https://frprf.ru/klienty/?REGION=77'):
    c, hd, b = get(u)
    h = b.decode('utf-8', 'replace')
    p = plain(h)
    rep.append(f'--- {u} -> {c} {len(h)} симв.')
    rep.append('   текст[300:1400]: ' + p[300:1400])

# 3) статистика заявок
for u in ('https://frprf.ru/proekty-i-zayavki/statistika-zayavok/',
          'https://frprf.ru/proekty-i-zayavki/'):
    c, hd, b = get(u)
    h = b.decode('utf-8', 'replace')
    ttl = re.search(r'<title[^>]*>(.*?)</title>', h, re.S)
    rep.append(f'--- {u} -> {c} {len(h)} | title='
               + (re.sub(r'\s+', ' ', ttl.group(1)).strip()[:60] if ttl else ''))
    if c == 200:
        rep.append('   ссылки-разделы: ' + str(sorted({x for x in re.findall(r'href="(/proekty[^"]{0,60})"', h)})[:20]))
        rep.append('   текст: ' + plain(h)[200:1200])

print('\n'.join(rep[-150:]))
sys.stdout.flush()
