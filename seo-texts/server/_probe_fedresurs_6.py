# -*- coding: utf-8 -*-
"""Проба 6: справочники типов сообщений, группы обременений, прайс платных услуг,
параметры оставшихся ручек (companies, pledged-subjects, monitorings, orders)."""
import io, sys, json, ssl, re, time
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')
B = 'https://fedresurs.ru/backend/'


def get(u, ref='https://fedresurs.ru/'):
    try:
        r = OP.open(urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': '*/*',
                                                       'Referer': ref}), timeout=45)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b''
    except Exception as e:
        return 0, repr(e)[:120].encode()


def jj(u, ref='https://fedresurs.ru/'):
    c, b = get(u, ref)
    try:
        return c, json.loads(b.decode('utf-8', 'replace'))
    except Exception:
        return c, None


sw = json.loads(get(B + 'swagger/v1/swagger.json')[1].decode('utf-8', 'replace'))
paths = sw.get('paths') or {}


def ptypes(s):
    if not isinstance(s, dict):
        return '?'
    if s.get('$ref'):
        return s['$ref'].split('/')[-1]
    if s.get('type') == 'array':
        return 'array<%s>' % ptypes(s.get('items') or {})
    return s.get('type') or '?'


print('=== A. параметры интересных ручек ===')
for p in ('/companies', '/companies/fast', '/pledged-subjects', '/real-estates',
          '/monitorings', '/monitorings/count', '/monitoring-subscribers',
          '/orders/prices', '/orders/rules', '/reference-book/regions',
          '/reference-book/message-types', '/reference-book/encumbrances-groups',
          '/sfact-messages/messagetypegroups', '/sfact-messages/{guid}', '/news'):
    op = (paths.get(p) or {})
    for m in ('get', 'post'):
        if m not in op:
            continue
        ps = ['%s=%s' % (x.get('name'), ptypes(x.get('schema') or {}))
              for x in (op[m].get('parameters') or [])]
        print('  %-5s %-36s %s' % (m.upper(), p, ' & '.join(ps) or '(без параметров)'))

print('\n=== B. /orders/prices — ОФИЦИАЛЬНЫЙ ПРАЙС ПЛАТНЫХ УСЛУГ ===')
c, d = jj(B + 'orders/prices')
print('  code=%s' % c)
print(json.dumps(d, ensure_ascii=False, indent=1)[:2500] if d is not None else '')

print('\n=== C. /orders/rules (первые 1200 символов) ===')
c, b = get(B + 'orders/rules')
print('  code=%s len=%s' % (c, len(b)))
print(b[:1200].decode('utf-8', 'replace'))

print('\n=== D. группы обременений + группы типов sfact ===')
for p in ('reference-book/encumbrances-groups', 'sfact-messages/messagetypegroups'):
    c, d = jj(B + p)
    print('  %s code=%s -> %s' % (p, c, json.dumps(d, ensure_ascii=False)[:1500]))

print('\n=== E. МОНИТОРИНГ (бесплатная подписка?) ===')
for p in ('monitorings/count', 'monitorings?limit=5&offset=0', 'settings/max'):
    c, b = get(B + p)
    print('  %-34s code=%s %s' % (p, c, b[:200].decode('utf-8', 'replace').replace('\n', ' ')))

print('\n=== F. СПРАВОЧНИК ТИПОВ СООБЩЕНИЙ (reference-book/message-types) ===')
c, d = jj(B + 'reference-book/message-types')
print('  code=%s тип ответа=%s' % (c, type(d).__name__))
if isinstance(d, list):
    print('  всего: %d' % len(d))
    if d:
        print('  поля: %s' % sorted(d[0].keys()))
    for x in d:
        s = json.dumps(x, ensure_ascii=False)
        print('   ' + s[:220])
elif isinstance(d, dict):
    print(json.dumps(d, ensure_ascii=False, indent=1)[:9000])
print('\n==== КОНЕЦ ПРОБЫ 6 ====')
