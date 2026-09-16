# -*- coding: utf-8 -*-
"""Проба 12: лимиты $top в $apply, счётчики по разделам КОСФН (startswith),
коды отраслевых разделов. Самое важное — В КОНЦЕ."""
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
API = 'https://open-api.egrz.ru/api/'
FROM = '2026-06-18T00:00:00Z'


def get(path, timeout=120):
    url = API + urllib.parse.quote(path, safe="/?&$=,()'*+:.-_%")
    h = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
         'Origin': 'https://egrz.ru', 'Referer': 'https://egrz.ru/'}
    try:
        r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, (e.read() if e.fp else b'')
    except Exception as e:  # noqa: BLE001
        return -1, ('ERR %s: %s' % (type(e).__name__, e)).encode()


def j(path):
    c, b = get(path)
    try:
        return c, json.loads(b.decode('utf-8'))
    except Exception:  # noqa: BLE001
        return c, {'_raw': b[:200].decode('utf-8', 'replace')}


TOPS = []
for t in (100, 150, 151, 200, 300, 500):
    c, d = j("PublicRegistrationBook?$apply=filter(ExpertiseConclusionDate gt %s)"
             "/groupby((FunctionalPurpose),aggregate($count as C))&$top=%d" % (FROM, t))
    TOPS.append((t, c, len(d.get('value') or []), str(d.get('_raw', ''))[:90]))

# счётчик через $count=true + $top=0 по разделам
SEC = []
for n in range(1, 21):
    p = '%02d.' % n
    c, d = j("PublicRegistrationBook?$count=true&$top=0&$filter=ExpertiseConclusionDate gt %s"
             " and startswith(FunctionalPurpose,'%s')" % (FROM, p))
    SEC.append((p, c, d.get('@odata.count'), str(d.get('_raw', ''))[:70]))

# коды отраслевых разделов
CODES = []
for n in list(range(5, 21)):
    p = '%02d.' % n
    c, d = j("PublicRegistrationBook?$apply=filter(ExpertiseConclusionDate gt %s"
             " and startswith(FunctionalPurpose,'%s'))"
             "/groupby((FunctionalPurpose),aggregate($count as C))&$top=100" % (FROM, p))
    for r in (d.get('value') or []):
        CODES.append((str(r.get('FunctionalPurpose') or ''), r.get('C') or 0))
# плюс промышленные вкрапления раздела 01
for p in ('01.01.006', '01.06.001'):
    c, d = j("PublicRegistrationBook?$apply=filter(ExpertiseConclusionDate gt %s"
             " and startswith(FunctionalPurpose,'%s'))"
             "/groupby((FunctionalPurpose),aggregate($count as C))&$top=100" % (FROM, p))
    for r in (d.get('value') or []):
        CODES.append((str(r.get('FunctionalPurpose') or ''), r.get('C') or 0))
CODES.sort(key=lambda x: x[1])

print('--- лимиты $top в $apply ---')
for t, c, n, raw in TOPS:
    print('   $top=%-5d code=%-5s строк=%-5d %s' % (t, c, n, raw))
print()
print('--- записей за 90 дней по разделам КОСФН ---')
for p, c, cnt, raw in SEC:
    print('   %-5s code=%-5s count=%-8s %s' % (p, c, cnt, raw))
print()
print('==== КОДЫ ОТРАСЛЕВЫХ РАЗДЕЛОВ + промплощадки (важное внизу) ====')
for n, c in CODES:
    print('%6d  %s' % (c, n[:120]))
print('ИТОГО: %d записей в %d кодах' % (sum(c for _, c in CODES), len(CODES)))
