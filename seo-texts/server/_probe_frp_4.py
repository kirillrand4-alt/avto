# -*- coding: utf-8 -*-
"""Проба 4: что за фильтр selOkved и карта vmap на главной ФРП — где данные проектов?
Только чтение сети + печать."""
import re
import ssl
import sys
import urllib.request

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


rep = []
c, b = get('https://frprf.ru/')
h = b.decode('utf-8', 'replace')
rep.append(f'главная {c} {len(h)}')

# контекст вокруг selOkved
for m in re.finditer(r'selOkved', h):
    s = max(0, m.start() - 900)
    frag = re.sub(r'\s+', ' ', h[s:m.start() + 900])
    rep.append('--- selOkved-контекст: ' + frag[:1800])
    break

# скрипты страницы (наши, не bitrix-ядро)
srcs = [s for s in re.findall(r'<script[^>]+src="([^"]+)"', h)
        if '/bitrix/js/main' not in s and '/bitrix/js/ui' not in s]
rep.append('--- script src (%d):' % len(srcs))
for s in srcs[:45]:
    rep.append('   ' + s[:130])

# инлайн-JS с упоминанием map/vmap/klient/proekt
for m in re.finditer(r'<script(?![^>]*src)[^>]*>(.*?)</script>', h, re.S):
    js = m.group(1)
    if re.search(r'vmap|jqvmap|mapData|klient|proekt|ajax', js, re.I):
        rep.append('--- инлайн-JS фрагмент: ' + re.sub(r'\s+', ' ', js)[:1200])

print('\n'.join(rep[-120:]))
sys.stdout.flush()
