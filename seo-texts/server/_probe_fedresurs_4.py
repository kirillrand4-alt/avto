# -*- coding: utf-8 -*-
"""Проба 4: разбор публичного OpenAPI fedresurs.ru (/backend/swagger/v1/swagger.json).
Печатаем маршруты, параметры поисковых эндпоинтов и перечисления типов сообщений.
Важное — ПОСЛЕДНИМ.
"""
import io, sys, json, ssl, re
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')


def get(url, referer='https://fedresurs.ru/'):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Referer': referer}
    try:
        r = OP.open(urllib.request.Request(url, headers=h), timeout=60)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, b''
    except Exception as e:
        return 0, repr(e)[:120].encode()


c, b = get('https://fedresurs.ru/backend/swagger/v1/swagger.json')
print('swagger code=%s len=%s' % (c, len(b)))
sw = json.loads(b.decode('utf-8', 'replace'))
paths = sw.get('paths') or {}
comps = (sw.get('components') or {}).get('schemas') or {}
print('title=%r version=%r путей=%d схем=%d' % ((sw.get('info') or {}).get('title'),
                                                (sw.get('info') or {}).get('version'),
                                                len(paths), len(comps)))

KEY = re.compile(r'sfact|message|publication|encumbr|search|compan|lease|pledge|licen|'
                 r'reorgan|bigdeal|deal|intention|invest|okved|region|dictionar|type', re.I)

print('\n=== A. ВСЕ пути (метод путь) ===')
for p in sorted(paths):
    ms = ','.join(sorted(m.upper() for m in paths[p] if m in ('get', 'post', 'put')))
    print('  %-6s %s' % (ms, p))


def params_of(p, method='get'):
    op = (paths.get(p) or {}).get(method) or {}
    out = []
    for pr in op.get('parameters') or []:
        sch = pr.get('schema') or {}
        t = sch.get('type') or sch.get('$ref', '').split('/')[-1]
        if sch.get('items'):
            t = 'array<%s>' % (sch['items'].get('type') or sch['items'].get('$ref', '').split('/')[-1])
        out.append('%s:%s(%s)' % (pr.get('name'), t, pr.get('in')))
    rb = ((op.get('requestBody') or {}).get('content') or {})
    for ct, v in rb.items():
        ref = (v.get('schema') or {}).get('$ref', '')
        if ref:
            out.append('BODY %s -> %s' % (ct, ref.split('/')[-1]))
    return out


print('\n=== B. параметры ключевых путей ===')
for p in sorted(paths):
    if KEY.search(p):
        for m in ('get', 'post'):
            if m in paths[p]:
                pp = params_of(p, m)
                if pp:
                    print('  %s %s' % (m.upper(), p))
                    print('     %s' % '; '.join(pp))

print('\n=== C. схемы-фильтры (тела запросов поиска) ===')
for name in sorted(comps):
    if re.search(r'(Filter|Request|Query|SearchParam)', name) and \
       re.search(r'sfact|message|publication|encumbr|search|compan', name, re.I):
        pr = (comps[name].get('properties') or {})
        line = '; '.join('%s:%s' % (k, (v.get('type') or v.get('$ref', '').split('/')[-1] or
                                        ('array<%s>' % ((v.get('items') or {}).get('type') or
                                                        (v.get('items') or {}).get('$ref', '').split('/')[-1]))))
                         for k, v in pr.items())
        print('  %s: %s' % (name, line[:900]))

print('\n=== D. ПЕРЕЧИСЛЕНИЯ ТИПОВ СООБЩЕНИЙ (enum) ===')
for name in sorted(comps):
    sch = comps[name]
    en = sch.get('enum')
    if en and len(en) >= 4 and re.search(r'type|kind|group|category', name, re.I):
        print('  %s (%d): %s' % (name, len(en), ', '.join(str(x) for x in en)[:2500]))
print('\n==== КОНЕЦ ПРОБЫ 4 ====')
