# -*- coding: utf-8 -*-
"""Проба 5: только карта маршрутов OpenAPI fedresurs.ru + параметры поисковых ручек."""
import io, sys, json, ssl, re
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')
r = OP.open(urllib.request.Request('https://fedresurs.ru/backend/swagger/v1/swagger.json',
                                   headers={'User-Agent': UA, 'Accept': '*/*',
                                            'Referer': 'https://fedresurs.ru/'}), timeout=60)
sw = json.loads(r.read().decode('utf-8', 'replace'))
paths, comps = sw.get('paths') or {}, (sw.get('components') or {}).get('schemas') or {}


def short(ref):
    return ref.split('/')[-1] if isinstance(ref, str) else ''


def ptypes(sch):
    if not isinstance(sch, dict):
        return '?'
    if sch.get('$ref'):
        return short(sch['$ref'])
    if sch.get('type') == 'array':
        return 'array<%s>' % ptypes(sch.get('items') or {})
    return sch.get('type') or '?'


SEL = re.compile(r'encumbr|sfact|message|publication|compan|search|bidding', re.I)
print('=== ПУТИ, относящиеся к поиску/сообщениям ===')
for p in sorted(paths):
    if not SEL.search(p):
        continue
    for m in ('get', 'post'):
        op = (paths[p] or {}).get(m)
        if not op:
            continue
        ps = []
        for pr in op.get('parameters') or []:
            ps.append('%s=%s' % (pr.get('name'), ptypes(pr.get('schema') or {})))
        body = ''
        for ct, v in ((op.get('requestBody') or {}).get('content') or {}).items():
            body = ' BODY:' + short((v.get('schema') or {}).get('$ref', ''))
        print('%s %s' % (m.upper(), p))
        if ps:
            print('     ? ' + ' & '.join(ps))
        if body:
            print('    ' + body)

print('\n=== ОСТАЛЬНЫЕ ПУТИ (только список) ===')
rest = [p for p in sorted(paths) if not SEL.search(p)]
for i in range(0, len(rest), 3):
    print('   ' + ' | '.join(rest[i:i + 3]))

print('\n=== СХЕМЫ-ФИЛЬТРЫ, использованные выше ===')
want = set()
for p in paths:
    if not SEL.search(p):
        continue
    for m in ('get', 'post'):
        op = (paths[p] or {}).get(m) or {}
        for ct, v in ((op.get('requestBody') or {}).get('content') or {}).items():
            want.add(short((v.get('schema') or {}).get('$ref', '')))
        for pr in op.get('parameters') or []:
            s = pr.get('schema') or {}
            if s.get('$ref'):
                want.add(short(s['$ref']))
            if (s.get('items') or {}).get('$ref'):
                want.add(short(s['items']['$ref']))
for n in sorted(x for x in want if x):
    sch = comps.get(n) or {}
    if sch.get('enum'):
        print('  ENUM %s (%d): %s' % (n, len(sch['enum']), ', '.join(map(str, sch['enum']))[:900]))
    else:
        pr = sch.get('properties') or {}
        print('  %s: %s' % (n, '; '.join('%s:%s' % (k, ptypes(v)) for k, v in pr.items())[:1200]))
print('\n==== КОНЕЦ ПРОБЫ 5 ====')
