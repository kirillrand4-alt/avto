# -*- coding: utf-8 -*-
"""Проба 1: достижим ли fedresurs.ru с РФ-сервера и какие у SPA backend-маршруты.

Только ЧТЕНИЕ сети + печать. Ничего не пишет в базы/флаги, провайдера не зовёт.
Важное печатаем ПОСЛЕДНИМ (stdout раннера режется сверху).
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


def get(url, referer=None, accept='text/html,application/xhtml+xml,*/*;q=0.8', timeout=30):
    h = {'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8'}
    if referer:
        h['Referer'] = referer
    req = urllib.request.Request(url, headers=h)
    t0 = time.time()
    try:
        r = OP.open(req, timeout=timeout)
        body = r.read()
        return {'code': r.getcode(), 'len': len(body), 'ms': int((time.time() - t0) * 1000),
                'hdr': dict(r.headers), 'body': body}
    except urllib.error.HTTPError as e:
        body = b''
        try:
            body = e.read()
        except Exception:
            pass
        return {'code': e.code, 'len': len(body), 'ms': int((time.time() - t0) * 1000),
                'hdr': dict(e.headers), 'body': body, 'err': 'HTTPError'}
    except Exception as e:
        return {'code': 0, 'len': 0, 'ms': int((time.time() - t0) * 1000),
                'hdr': {}, 'body': b'', 'err': repr(e)[:200]}


def brief(tag, r, show=260):
    txt = (r['body'][:show].decode('utf-8', 'replace').replace('\n', ' ').replace('\r', ' ')
           if r['body'] else '')
    srv = r['hdr'].get('Server', '')
    ct = r['hdr'].get('Content-Type', '')
    sc = r['hdr'].get('Set-Cookie', '')[:120]
    print('[%s] code=%s len=%s ms=%s server=%r ct=%r err=%s' %
          (tag, r['code'], r['len'], r['ms'], srv, ct, r.get('err', '')))
    if sc:
        print('      set-cookie: %s' % sc)
    if txt:
        print('      body: %s' % txt)


out = []

# 1. внешний IP сервера (подтвердить, что запросы идут с РФ-адреса)
r = get('https://api.ipify.org?format=json', accept='application/json', timeout=20)
brief('ipify', r, 120)

# 2. robots.txt
r_rob = get('https://fedresurs.ru/robots.txt', accept='text/plain')
brief('robots.txt', r_rob, 700)

# 3. главная
r_main = get('https://fedresurs.ru/')
brief('main', r_main, 300)

# 4. backend: поиск компании по ИНН (как в статье на Хабре, с Referer)
inn = '7707083893'  # Сбербанк — публичный ИНН для теста
r_c = get('https://fedresurs.ru/backend/companies?limit=15&offset=0&code=' + inn,
          referer='https://fedresurs.ru/search/entity?code=' + inn,
          accept='application/json, text/plain, */*')
brief('backend/companies?code', r_c, 600)

# 5. то же БЕЗ Referer — проверить, правда ли Referer обязателен
r_c2 = get('https://fedresurs.ru/backend/companies?limit=15&offset=0&code=' + inn,
           accept='application/json, text/plain, */*')
brief('backend/companies БЕЗ Referer', r_c2, 300)

# 6. кандидаты на ленту сообщений (угадываем маршруты SPA)
CAND = [
    ('sfactmessages', 'https://fedresurs.ru/backend/sfactmessages?limit=15&offset=0'),
    ('sfacts', 'https://fedresurs.ru/backend/sfacts?limit=15&offset=0'),
    ('messages', 'https://fedresurs.ru/backend/messages?limit=15&offset=0'),
    ('publications', 'https://fedresurs.ru/backend/publications?limit=15&offset=0'),
    ('search/sfacts', 'https://fedresurs.ru/backend/search/sfacts?limit=15&offset=0'),
    ('encumbrances', 'https://fedresurs.ru/backend/encumbrances?limit=15&offset=0'),
]
for tag, u in CAND:
    rr = get(u, referer='https://fedresurs.ru/search/message',
             accept='application/json, text/plain, */*', timeout=20)
    brief('cand:' + tag, rr, 220)

# 7. ГЛАВНОЕ: вытащить backend-маршруты из JS-бандлов SPA
routes = set()
js_report = []
if r_main['body']:
    html = r_main['body'].decode('utf-8', 'replace')
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', html)
    links = re.findall(r'<link[^>]+href="([^"]+\.js)"', html)
    cand = []
    for s in (srcs + links):
        if s.startswith('//'):
            s = 'https:' + s
        elif s.startswith('/'):
            s = 'https://fedresurs.ru' + s
        if s.startswith('http') and 'fedresurs.ru' in s:
            cand.append(s)
    seen = set()
    for u in cand[:14]:
        if u in seen:
            continue
        seen.add(u)
        rj = get(u, referer='https://fedresurs.ru/', accept='*/*', timeout=45)
        js_report.append((u.split('/')[-1][:50], rj['code'], rj['len']))
        if rj['code'] == 200 and rj['body']:
            txt = rj['body'].decode('utf-8', 'replace')
            for m in re.findall(r'["\'`/]((?:backend|api)/[A-Za-z0-9_\-/{}$.]{2,70})', txt):
                routes.add(m)

print('\n==== JS-бандлы (имя, код, размер) ====')
for x in js_report:
    print('   %s  code=%s len=%s' % x)

print('\n==== BACKEND-МАРШРУТЫ ИЗ БАНДЛОВ (%d шт) ====' % len(routes))
for x in sorted(routes):
    print('   ' + x)
print('\n==== КОНЕЦ ПРОБЫ 1 ====')
