# -*- coding: utf-8 -*-
"""Проба 17: доказательная база для документа — где НЕТ сметной стоимости,
что отдают выгрузки (openDataFile/excelDataFile/xmlDataFile), ТЭП, Analytics/Statistic,
и есть ли лимит/капча при частых запросах. Важное — В КОНЦЕ."""
import ssl
import time
import json
import urllib.request
import urllib.error
import urllib.parse

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
API = 'https://open-api.egrz.ru/api/'


def call(url, data=None, method=None, timeout=60):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Origin': 'https://egrz.ru',
         'Referer': 'https://egrz.ru/'}
    if data is not None:
        h['Content-Type'] = 'application/json'
    try:
        r = _OP.open(urllib.request.Request(url, headers=h, data=data, method=method),
                     timeout=timeout)
        return r.getcode(), dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), (e.read() if e.fp else b'')
    except Exception as e:  # noqa: BLE001
        return -1, {}, ('ERR %s: %s' % (type(e).__name__, e)).encode()


R = []


def show(tag, url, data=None, method=None):
    c, h, b = call(url, data, method)
    R.append((tag, c, str(h.get('Content-Type', ''))[:28], len(b),
              b[:220].decode('utf-8', 'replace').replace('\n', ' ')))


# 1. выгрузки (GET и POST)
for ep in ('openDataFile', 'excelDataFile', 'xmlDataFile'):
    show('GET ' + ep, API + 'PublicRegistrationBook/' + ep)
    show('POST ' + ep, API + 'PublicRegistrationBook/' + ep,
         data=json.dumps({'filter': ''}).encode(), method='POST')

# 2. ТЭП и аналитика
show('getTepValues', API + 'dictionary/getTepValues')
show('Analytics', API + 'Analytics?$top=2')
show('Statistic', API + 'Statistic?$top=2')
show('organizations', API + 'organizations?$top=2')

# 3. поля с намёком на стоимость — сервер перечислит тип, если поля нет
for f in ('SmetnayaStoimost', 'Price', 'Sum', 'TEP', 'Tep'):
    show('$select=' + f, API + "PublicRegistrationBook?$top=1&$select=" + f)

# 4. частота: 25 запросов подряд — ловим 429/капчу
t0 = time.time()
codes = []
for i in range(25):
    c, h, b = call(API + "PublicRegistrationBook?%%24top=1&%%24skip=%d&%%24select=Key" % (i * 7))
    codes.append(c)
burst = '%.1f с, коды: %s' % (time.time() - t0, sorted(set(codes)))

print('==================== ИТОГ ====================')
for tag, c, ct, ln, head in R:
    print('%-18s code=%-5s ct=%-28s len=%-9d %s' % (tag, c, ct, ln, head[:180]))
print()
print('залп 25 запросов подряд:', burst)
