# -*- coding: utf-8 -*-
"""Проба 7: прайс, группы обременений, типы сообщений НЕ-банкротного проекта (ЕФРСФДЮЛ),
параметры ручек companies/pledged-subjects/monitorings."""
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


def jj(u):
    c, b = get(u)
    try:
        return c, json.loads(b.decode('utf-8', 'replace'))
    except Exception:
        return c, None


sw = json.loads(get(B + 'swagger/v1/swagger.json')[1].decode('utf-8', 'replace'))
paths = sw.get('paths') or {}


def pt(s):
    if not isinstance(s, dict):
        return '?'
    if s.get('$ref'):
        return s['$ref'].split('/')[-1].split('.')[-1]
    if s.get('type') == 'array':
        return 'array<%s>' % pt(s.get('items') or {})
    return s.get('type') or '?'


print('=== A. параметры ручек ===')
for p in ('/companies', '/companies/fast', '/companies/{guid}', '/companies/{guid}/licenses',
          '/companies/{guid}/encumbrances', '/pledged-subjects', '/real-estates',
          '/monitorings', '/monitoring-subscribers', '/orders/prices', '/news',
          '/reference-book/regions', '/reference-book/message-types'):
    op = paths.get(p) or {}
    for m in ('get', 'post'):
        if m in op:
            ps = ['%s=%s' % (x.get('name'), pt(x.get('schema') or {}))
                  for x in (op[m].get('parameters') or [])]
            print('  %-5s %-34s %s' % (m.upper(), p, ' & '.join(ps) or '(нет параметров)'))

print('\n=== B. группы обременений ===')
c, d = jj(B + 'reference-book/encumbrances-groups')
print('  code=%s %s' % (c, json.dumps(d, ensure_ascii=False)[:1200]))

print('\n=== C. /orders/prices ===')
c, d = jj(B + 'orders/prices')
print('  code=%s' % c)
print(json.dumps(d, ensure_ascii=False, indent=1)[:2000] if d is not None else '')

print('\n=== D. мониторинг: сколько стоит/нужен ли логин ===')
for p in ('monitorings/count', 'settings/max', 'monitorings?Limit=5&Offset=0'):
    c, b = get(B + p)
    print('  %-30s code=%s %s' % (p, c, b[:220].decode('utf-8', 'replace').replace('\n', ' ')))

print('\n=== E. ТИПЫ СООБЩЕНИЙ ЕФРСФДЮЛ (project != 1) ===')
c, d = jj(B + 'reference-book/message-types')
if isinstance(d, list):
    from collections import Counter
    print('  всего типов: %d, по project: %s' % (len(d), dict(Counter(x.get('project') for x in d))))
    for x in d:
        if x.get('project') != 1 and not x.get('isOld'):
            print('   %-42s %s' % (x.get('code'), (x.get('name') or '')[:150]))
print('\n==== КОНЕЦ ПРОБЫ 7 ====')
