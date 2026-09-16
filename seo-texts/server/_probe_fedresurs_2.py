# -*- coding: utf-8 -*-
"""Проба 2: разведка backend-маршрутов fedresurs.ru + структура данных.

Только ЧТЕНИЕ сети + печать. Важное — ПОСЛЕДНИМ.
"""
import io, re, sys, json, ssl, time
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')


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


print('=== A. robots.txt полностью ===')
c, b = get('https://fedresurs.ru/robots.txt', accept='text/plain')
print('code=%s\n%s' % (c, b.decode('utf-8', 'replace')))

print('\n=== B. sitemap / служебные ===')
for u in ('https://fedresurs.ru/sitemap.xml', 'https://fedresurs.ru/asset-manifest.json',
          'https://fedresurs.ru/index.html', 'https://fedresurs.ru/manifest.json'):
    c, b = get(u, accept='*/*')
    print('  %-46s code=%s len=%s  %s' % (u.split('/')[-1], c, len(b),
                                          b[:110].decode('utf-8', 'replace').replace('\n', ' ')))

print('\n=== C. Свип кандидатов маршрутов /backend/* ===')
CAND = [
    'sfactmessages/search', 'sfactmessage/search', 'sfacts/search', 'publications/search',
    'messages/search', 'search/publications', 'search/messages', 'search/sfactmessages',
    'sfactmessages/list', 'publications', 'pubs', 'sfactpublications',
    'companies/search', 'persons/search', 'realestate/search', 'fnp-search',
    'encumbrances/search', 'encumbrances/types', 'encumbrancetypes',
    'dictionary/sfacttypes', 'dictionaries/messagetypes', 'sfacttypes', 'messagetypes',
    'dictionary', 'dictionaries', 'regions', 'okveds',
    'news', 'biddings', 'biddings/search', 'reports', 'priorityoffers',
    'bankrupts/search', 'bankruptmessages/search', 'firmbankruptmessages/search',
    'amreports/search', 'legalcases/search', 'sroreports/search',
    'auditreports/search', 'licenses/search', 'reorganizations/search',
]
for p in CAND:
    u = 'https://fedresurs.ru/backend/' + p + '?limit=5&offset=0'
    c, b = get(u)
    flag = 'OK ' if c == 200 else '   '
    print('  %s%-34s code=%s len=%s %s' % (flag, p, c, len(b),
                                           b[:90].decode('utf-8', 'replace').replace('\n', ' ')))

print('\n=== D. companies?code=<ИНН промышленной> -> guid -> publications ===')
INN = '1650032058'  # ПАО «КАМАЗ»
c, d = jget('https://fedresurs.ru/backend/companies?limit=5&offset=0&code=' + INN,
            referer='https://fedresurs.ru/search/entity?code=' + INN)
print('  companies code=%s' % c)
guid = None
if d and d.get('pageData'):
    row = d['pageData'][0]
    guid = row.get('guid')
    print('  поля компании: %s' % sorted(row.keys()))
    print('  %s / ИНН %s / guid %s' % (row.get('name'), row.get('inn'), guid))
if guid:
    for q in ('?limit=10&offset=0',
              '?limit=10&offset=0&searchSfactsMessage=true',
              '?limit=10&offset=0&searchFirmBankruptMessage=true&searchSfactsMessage=true'
              '&searchCompanyEfrsb=true&searchAmReport=true&searchLegalCase=true'):
        c, d2 = jget('https://fedresurs.ru/backend/companies/%s/publications%s' % (guid, q),
                     referer='https://fedresurs.ru/company/' + guid)
        n = len((d2 or {}).get('pageData') or []) if isinstance(d2, dict) else -1
        print('  publications%s -> code=%s items=%s total=%s' %
              (q[:42], c, n, (d2 or {}).get('found') if isinstance(d2, dict) else ''))
        if n > 0:
            it = d2['pageData'][0]
            print('     поля сообщения: %s' % sorted(it.keys()))
            print('     пример: %s' % json.dumps(it, ensure_ascii=False)[:700])

print('\n=== E. /backend/encumbrances — ЛЕНТА (сортировка, параметры) ===')
c, d = jget('https://fedresurs.ru/backend/encumbrances?limit=3&offset=0')
print('  code=%s ключи ответа=%s' % (c, sorted((d or {}).keys()) if isinstance(d, dict) else None))
if isinstance(d, dict) and d.get('pageData'):
    print('  found/total: %s' % {k: v for k, v in d.items() if k != 'pageData'})
    for it in d['pageData'][:2]:
        print('  ---- сообщение ----')
        print(json.dumps(it, ensure_ascii=False, indent=1)[:1800])

print('\n=== F. encumbrances с фильтрами (типы/даты/ИНН) ===')
for q in ('?limit=3&offset=0&types=FinancialLeaseContract',
          '?limit=3&offset=0&publishDateStart=2026-09-01&publishDateEnd=2026-09-16',
          '?limit=3&offset=0&searchString=1650032058',
          '?limit=3&offset=0&code=1650032058',
          '?limit=3&offset=0&inn=1650032058',
          '?limit=3&offset=0&isActual=true&group=Lease'):
    c, d = jget('https://fedresurs.ru/backend/encumbrances' + q)
    n = len((d or {}).get('pageData') or []) if isinstance(d, dict) else -1
    first = ''
    if n > 0:
        first = str(d['pageData'][0].get('type')) + ' ' + str(d['pageData'][0].get('publishDate'))
    print('  %-62s code=%s items=%s %s' % (q, c, n, first))

print('\n==== КОНЕЦ ПРОБЫ 2 ====')
