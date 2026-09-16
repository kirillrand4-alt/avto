# -*- coding: utf-8 -*-
"""Проба 7: region_js (данные карты на главной) + «истории успеха» + что ещё осталось от реестра."""
import json
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


def get(url, timeout=30, headers=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    try:
        r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:                                    # noqa: BLE001
            return e.code, b''
    except Exception as e:                                   # noqa: BLE001
        return -1, str(e)[:150].encode()


rep = []
c, b = get('https://frprf.ru/')
h = b.decode('utf-8', 'replace')

m = re.search(r'region_js\s*=\s*', h)
rep.append(f'главная {c} {len(h)}; region_js найден: {bool(m)}')
if m:
    # вырезаем сбалансированный JSON-объект
    i = h.index('{', m.end())
    depth, j = 0, i
    while j < len(h):
        if h[j] == '{':
            depth += 1
        elif h[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    raw = h[i:j + 1]
    rep.append(f'   размер region_js: {len(raw)} симв.')
    try:
        d = json.loads(raw)
        rep.append(f'   регионов: {len(d)}')
        k0 = list(d)[:3]
        for k in k0:
            v = d[k]
            rep.append(f'   регион {k}: ключи {list(v)[:20] if isinstance(v, dict) else type(v)}')
            rep.append('     значение (обрез): ' + json.dumps(v, ensure_ascii=False)[:900])
    except Exception as e:                                   # noqa: BLE001
        rep.append('   не JSON: ' + str(e)[:120] + ' | начало: ' + raw[:500])

# «истории успеха»
links = sorted(set(re.findall(r'href="(/press-tsentr/[^"?#]{4,90}/)"', h)))
rep.append(f'--- ссылок press-tsentr на главной: {len(links)}; примеры: ' + ' | '.join(links[:6]))

# что лежит по «Реестр ОПК» и «Навигатор ГИСП»
for u in ('https://frprf.ru/navigator-gospodderzhky/opk/',
          'https://frprf.ru/navigator-gospodderzhky/'):
    c2, b2 = get(u)
    h2 = b2.decode('utf-8', 'replace')
    ttl = re.search(r'<title[^>]*>(.*?)</title>', h2, re.S)
    ext = sorted({x for x in re.findall(r'href="(https?://(?!frprf\.ru)[^"]{6,70})"', h2)})
    rep.append(f'  {c2} {len(h2):>7} {u} | title='
               + (re.sub(r'\s+', ' ', ttl.group(1)).strip()[:60] if ttl else ''))
    rep.append('    внешние ссылки: ' + str(ext[:12]))

print('\n'.join(rep[-120:]))
sys.stdout.flush()
