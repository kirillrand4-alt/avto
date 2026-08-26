# -*- coding: utf-8 -*-
"""promrnd: точная разметка ссылки «Перейти на сайт компании» + что за домен
xn--d1acmcsfk8d0a.xn--p1ai (мой общий сборщик хостов его нахватал)."""
import io
import json
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')


def get(url, tmo=35):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'}), timeout=tmo) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception as e:
        return -1, str(e)[:60]


R = {'домен_punycode': 'xn--d1acmcsfk8d0a.xn--p1ai'}
try:
    R['домен_расшифровка'] = 'xn--d1acmcsfk8d0a.xn--p1ai'.encode().decode('idna')
except Exception as e:
    R['домен_расшифровка'] = 'не разобрал: ' + str(e)[:40]
for i in (33, 1, 100):
    st, h = get('https://promrnd.ru/company/%d/' % i)
    if st != 200:
        R['карточка_%d' % i] = {'st': st}
        continue
    m = re.search(r'.{300}Перейти на сайт компании', h, re.S)
    R['карточка_%d' % i] = {
        'st': st,
        'разметка_вокруг_ссылки': re.sub(r'\s+', ' ', m.group(0))[-320:] if m else 'не нашёл',
        'все_внешние': sorted({u.split('/', 3)[2] for u in
                               re.findall(r'href="(https?://[^"]+)"', h)})[:12]}
    time.sleep(1.4)
print(json.dumps(R, ensure_ascii=False)[:4500])
