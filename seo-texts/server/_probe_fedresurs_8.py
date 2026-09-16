# -*- coding: utf-8 -*-
"""Проба 8: компактный ПОЛНЫЙ список путей API + прайс + параметры ключевых ручек."""
import io, sys, json, ssl
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')
B = 'https://fedresurs.ru/backend/'


def get(u):
    try:
        r = OP.open(urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': '*/*',
                                                       'Referer': 'https://fedresurs.ru/'}), timeout=45)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b''
    except Exception as e:
        return 0, repr(e)[:120].encode()


sw = json.loads(get(B + 'swagger/v1/swagger.json')[1].decode('utf-8', 'replace'))
paths = sorted(sw.get('paths') or {})
print('=== ВСЕ ПУТИ API (%d) ===' % len(paths))
for i in range(0, len(paths), 3):
    print('  ' + ' | '.join(paths[i:i + 3]))


def pt(s):
    if not isinstance(s, dict):
        return '?'
    if s.get('$ref'):
        return s['$ref'].split('/')[-1].split('.')[-1]
    if s.get('type') == 'array':
        return 'array<%s>' % pt(s.get('items') or {})
    return s.get('type') or '?'


print('\n=== ПАРАМЕТРЫ ===')
for p in ('/companies', '/companies/fast', '/companies/{guid}', '/companies/{guid}/licenses',
          '/companies/{guid}/encumbrances', '/pledged-subjects', '/monitorings',
          '/orders/prices', '/encumbrances', '/reference-book/regions'):
    op = (sw['paths'].get(p) or {})
    for m in ('get', 'post'):
        if m in op:
            ps = ['%s=%s' % (x.get('name'), pt(x.get('schema') or {}))
                  for x in (op[m].get('parameters') or [])]
            print('  %-5s %-32s %s' % (m.upper(), p, ' & '.join(ps) or '(нет)'))

print('\n=== /backend/orders/prices ===')
c, b = get(B + 'orders/prices')
print('  code=%s len=%s' % (c, len(b)))
print(b[:1800].decode('utf-8', 'replace'))
print('\n=== /backend/reference-book/encumbrances-groups ===')
c, b = get(B + 'reference-book/encumbrances-groups')
print('  code=%s %s' % (c, b[:900].decode('utf-8', 'replace')))
print('\n==== КОНЕЦ ПРОБЫ 8 ====')
