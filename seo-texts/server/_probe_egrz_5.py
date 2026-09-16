# -*- coding: utf-8 -*-
"""Проба 5: точный конфиг базовых URL из бандла egrz.ru (кто такой publicAPI).
Печатаем КОМПАКТНО и ПОСЛЕДНИМ."""
import re
import ssl
import urllib.request
import urllib.error

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
BASE = 'https://egrz.ru'


def get(url, timeout=60):
    try:
        r = _OP.open(urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'}),
                     timeout=timeout)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, (e.read() if e.fp else b'')
    except Exception as e:  # noqa: BLE001
        return -1, ('ERR %s: %s' % (type(e).__name__, e)).encode()


c, b = get(BASE + '/')
scripts = re.findall(r'<script[^>]+src="([^"]+)"', b.decode('utf-8', 'replace'))
big = ''
for s in scripts:
    u = s if s.startswith('http') else BASE + '/' + s.lstrip('/')
    cc, bb = get(u)
    print('js', s[:50], cc, len(bb))
    if cc == 200 and b'publicAPI' in bb:
        big = bb.decode('utf-8', 'replace')
        name = s
        break

hosts = sorted(set(re.findall(r'https?://[A-Za-z0-9_\-\.]*egrz\.ru[A-Za-z0-9_\-/\.]*', big)))
# присваивания вида n.xxx="..." рядом с publicAPI
i = big.find('publicAPI=')
chunk = big[max(0, i - 2500):i + 2500] if i > 0 else ''
assigns = re.findall(r'([A-Za-z_][A-Za-z0-9_]{2,30})\s*=\s*"([^"]{0,160})"', chunk)

print()
print('==================== ИТОГ ====================')
print('бандл:', name if big else 'НЕ НАЙДЕН')
print('--- все *.egrz.ru URL в бандле (%d) ---' % len(hosts))
for hh in hosts[:40]:
    print('  ', hh[:160])
print('--- присваивания рядом с publicAPI (%d) ---' % len(assigns))
for k, v in assigns[:80]:
    print('   %-28s = %s' % (k[:28], v[:120]))
print('--- сырой кусок вокруг publicAPI= ---')
print(chunk[2200:3400].replace('\n', ' ') if chunk else '(нет)')
