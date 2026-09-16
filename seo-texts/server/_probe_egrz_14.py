# -*- coding: utf-8 -*-
"""Проба 14: маршруты публичного сайта egrz.ru (как выглядит ссылка на заключение)
+ проверка одиночной записи по ключу. Важное — В КОНЦЕ."""
import re
import ssl
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


def get(url, timeout=90):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Origin': 'https://egrz.ru',
         'Referer': 'https://egrz.ru/'}
    try:
        r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, (e.read() if e.fp else b'')
    except Exception as e:  # noqa: BLE001
        return -1, ('ERR %s: %s' % (type(e).__name__, e)).encode()


c, b = get('https://egrz.ru/main.bundle.js')
big = b.decode('utf-8', 'replace') if c == 200 else ''
routes = sorted(set(re.findall(r'path\s*:\s*"([^"]{0,60})"', big)))
book_ctx = []
for m in list(re.finditer(r'.{50}(?:registration-book|registrationBook|reestr|registry).{110}', big))[:200]:
    s = m.group(0)
    if 'path:' in s or 'routerLink' in s or 'navigate' in s or 'href' in s:
        book_ctx.append(s)

# одиночная запись по ключу
c2, b2 = get("https://open-api.egrz.ru/api/PublicRegistrationBook?$top=1"
             "&$orderby=ExpertiseConclusionDate%20desc&$select=Key,ExpertiseNumber")
key = num = ''
try:
    v = json.loads(b2.decode('utf-8'))['value'][0]
    key, num = v.get('Key'), v.get('ExpertiseNumber')
except Exception:  # noqa: BLE001
    pass
ONE = []
for u in ("https://open-api.egrz.ru/api/PublicRegistrationBook('%s')" % key,
          "https://open-api.egrz.ru/api/PublicRegistrationBook?$filter=Key%%20eq%%20%s" % key,
          "https://open-api.egrz.ru/api/PublicRegistrationBook?$filter=ExpertiseNumber%%20eq%%20'%s'"
          % urllib.parse.quote(num or '')):
    c3, b3 = get(u)
    ONE.append((u[:110], c3, len(b3), b3[:150].decode('utf-8', 'replace').replace('\n', ' ')))

print('--- маршруты Angular (%d) ---' % len(routes))
for r in routes:
    print('   ', r[:70])
print()
print('--- контексты reestr/registration-book (%d) ---' % len(book_ctx))
for s in book_ctx[:12]:
    print('   ', s.replace('\n', ' ')[:200])
print()
print('==== одиночная запись (Key=%s, №=%s) ====' % (key, num))
for u, c3, ln, head in ONE:
    print('%-112s code=%-5s len=%-7d %s' % (u, c3, ln, head[:130]))
