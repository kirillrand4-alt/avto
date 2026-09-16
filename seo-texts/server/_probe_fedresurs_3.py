# -*- coding: utf-8 -*-
"""Проба 3: детальная карточка сообщения, параметры фильтрации ленты обременений,
поиск эндпоинта ленты сообщений ЕФРСФДЮЛ. Только чтение + печать.
"""
import io, re, sys, json, ssl, time, http.cookiejar
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX),
                                 urllib.request.HTTPCookieProcessor(CJ))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')
B = 'https://fedresurs.ru/backend/'


def get(url, referer='https://fedresurs.ru/', accept='application/json, text/plain, */*', timeout=25):
    h = {'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'ru-RU,ru;q=0.9'}
    if referer:
        h['Referer'] = referer
    try:
        r = OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        try:
            b = e.read()
        except Exception:
            b = b''
        return e.code, b
    except Exception as e:
        return 0, repr(e)[:150].encode()


def jget(url, referer='https://fedresurs.ru/'):
    c, b = get(url, referer=referer)
    try:
        return c, json.loads(b.decode('utf-8', 'replace'))
    except Exception:
        return c, None


# прогреть куки нормальным запросом
get('https://fedresurs.ru/robots.txt', accept='text/plain')

print('=== A. bankrot.fedresurs.ru с РФ-IP ===')
for u in ('https://bankrot.fedresurs.ru/', 'https://old.bankrot.fedresurs.ru/'):
    c, b = get(u, referer=None, accept='text/html,*/*')
    print('  %-40s code=%s len=%s %s' % (u, c, len(b), b[:80].decode('utf-8', 'replace').replace('\n', ' ')))

print('\n=== B. детальная карточка сообщения ===')
GU = ['37176051-0621-4e7e-af3c-e915d212c58d', '09ffe994-91ee-4992-8fc3-ddb6fc7b0f63']
for g in GU:
    for path in ('sfactmessages/', 'sfactmessage/', 'messages/'):
        c, b = get(B + path + g, referer='https://fedresurs.ru/sfactmessages/' + g)
        print('  %-18s%s code=%s len=%s' % (path, g[:8], c, len(b)))
        if c == 200 and len(b) > 10:
            try:
                d = json.loads(b.decode('utf-8', 'replace'))
                print('     ключи: %s' % sorted(d.keys())[:40])
                print('     json: %s' % json.dumps(d, ensure_ascii=False)[:1400])
            except Exception as e:
                print('     не json: %s' % b[:200].decode('utf-8', 'replace'))
            break

print('\n=== C. ещё кандидаты ленты сообщений ЕФРСФДЮЛ ===')
for p in ('sfactmessages/list', 'sfactmessages/page', 'sfactmessages/find',
          'messages/find', 'search', 'search/entity', 'search/sfact',
          'companies/publications', 'publications/list', 'sfact/search',
          'sfactmessages?limit=5&offset=0&_=1', 'encumbrances/list',
          'nonresidentcompanies/search', 'realestate/search', 'fnp-search',
          'companies/search', 'swagger/v1/swagger.json', 'swagger/index.html'):
    u = B + p + ('' if '?' in p else '?limit=5&offset=0')
    c, b = get(u, referer='https://fedresurs.ru/search/encumbrances')
    print('  %s%-38s code=%s len=%s %s' % ('OK ' if c == 200 else '   ', p, c, len(b),
                                           b[:70].decode('utf-8', 'replace').replace('\n', ' ')))

print('\n=== D. publications по компании — гоняем 451 ===')
c, d = jget(B + 'companies?limit=1&offset=0')
g = (d or {}).get('pageData', [{}])[0].get('guid') if isinstance(d, dict) else None
print('  guid компании: %s' % g)
if g:
    for ref in ('https://fedresurs.ru/company/' + g, 'https://fedresurs.ru/', None):
        c, b = get(B + 'companies/%s/publications?limit=5&offset=0' % g, referer=ref)
        print('  ref=%-42s code=%s len=%s %s' % (str(ref)[-42:], c, len(b),
                                                 b[:120].decode('utf-8', 'replace').replace('\n', ' ')))
    c, b = get(B + 'companies/%s' % g, referer='https://fedresurs.ru/company/' + g)
    print('  карточка компании: code=%s len=%s %s' % (c, len(b), b[:300].decode('utf-8', 'replace')))

print('\n=== E. ПАРАМЕТРЫ ЛЕНТЫ /backend/encumbrances (по числу found) ===')
base = B + 'encumbrances?limit=1&offset=0'
c, d = jget(base)
print('  БАЗА: found=%s' % (d or {}).get('found'))
TESTS = [
    '&types=FinancialLeaseContract2', '&type=FinancialLeaseContract2',
    '&messageTypes=FinancialLeaseContract2', '&encumbranceTypes=FinancialLeaseContract2',
    '&group=Lease', '&groups=Lease', '&kinds=Lease', '&kind=Lease',
    '&searchString=1650032058', '&searchString=%D0%9A%D0%90%D0%9C%D0%90%D0%97',
    '&publishDateStart=2026-09-10', '&publishDateEnd=2026-09-10',
    '&publishDateStart=2026-09-10&publishDateEnd=2026-09-16',
    '&regions=16', '&region=16', '&okved=28', '&isActual=true', '&isActual=false',
    '&roles=Lessee', '&subjectType=Company', '&onlyCompanies=true',
    '&pledgeTypes=Pledge', '&contractTypes=Lease', '&messageType=FinancialLeaseContract2',
]
for t in TESTS:
    c2, d2 = jget(base + t)
    f = (d2 or {}).get('found') if isinstance(d2, dict) else None
    first = ''
    if isinstance(d2, dict) and d2.get('pageData'):
        it = d2['pageData'][0]
        first = '%s %s' % (it.get('type'), (it.get('publishDate') or '')[:10])
    print('  %-58s code=%s found=%-7s %s' % (t, c2, f, first))

print('\n=== F. глубина offset и лимит ===')
for off in (100, 1000, 9990, 10000, 20000):
    c2, d2 = jget(base.replace('limit=1', 'limit=5') + '&offset=%d' % off)
    n = len((d2 or {}).get('pageData') or []) if isinstance(d2, dict) else -1
    dt = (d2['pageData'][0].get('publishDate') if n > 0 else '')
    print('  offset=%-6s code=%s items=%s first=%s' % (off, c2, n, dt))
for lim in (50, 100, 200, 500):
    c2, d2 = jget(B + 'encumbrances?offset=0&limit=%d' % lim)
    n = len((d2 or {}).get('pageData') or []) if isinstance(d2, dict) else -1
    print('  limit=%-5s code=%s items=%s' % (lim, c2, n))

print('\n=== G. РАСПРЕДЕЛЕНИЕ ТИПОВ в ленте (300 свежих) ===')
from collections import Counter
cnt = Counter()
roles = Counter()
inn_ok = 0
tot = 0
for off in range(0, 300, 100):
    c2, d2 = jget(B + 'encumbrances?limit=100&offset=%d' % off)
    for it in (d2 or {}).get('pageData') or []:
        tot += 1
        cnt[it.get('type')] += 1
        for s in (it.get('weakSide') or []) + (it.get('strongSide') or []):
            roles[(s.get('type'), s.get('role'))] += 1
            if s.get('inn'):
                inn_ok += 1
    time.sleep(0.4)
print('  всего сообщений: %s, сторон с непустым ИНН: %s' % (tot, inn_ok))
for k, v in cnt.most_common(30):
    print('   тип %-34s %s' % (k, v))
for k, v in roles.most_common(20):
    print('   сторона %-30s %s' % (str(k), v))
print('\n==== КОНЕЦ ПРОБЫ 3 ====')
