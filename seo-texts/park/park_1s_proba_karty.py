# -*- coding: utf-8 -*-
"""Проба карточки парка после обновления базы панели: видны ли марки, ссылки и снимки.

Смотрим не «200 OK», а содержимое: сколько фактов на странице, сколько ссылок-доказательств,
есть ли картинка снимка и обозначение машины. Иначе «панель обновилась» — это слово, а не факт.

Карточки парка живут за входом приложения (HTTP Basic пускает по сегменту /centro/, но
дальше своя сессия), поэтому сперва логинимся тем же способом, что и проба перехода.
"""
import http.cookiejar, io, os, re, sys, urllib.parse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
B = 'http://127.0.0.1:8012/obzvon'
PW = ''
if os.path.exists(r'C:\sender\centro-user3.txt'):
    t = open(r'C:\sender\centro-user3.txt', encoding='utf-8', errors='replace').read()
    m = re.search(r'(?:пароль|password)\s*[:=]\s*(\S+)', t, re.I)
    PW = m.group(1) if m else t.strip().split()[-1]
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open(B + '/centro/login', timeout=30)
op.open(urllib.request.Request(B + '/centro/login', data=urllib.parse.urlencode(
    {'username': 'user3', 'password': PW}).encode()), timeout=40)

for inn in ('6320004728', '0268004714', '2130230898'):
    try:
        with op.open('%s/centro/park/%s' % (B, inn), timeout=90) as r:
            t = r.read().decode('utf-8', 'replace')
            kod = r.status
    except Exception as e:  # noqa: BLE001
        print('%s -> ОШИБКА %s' % (inn, str(e)[:120]))
        continue
    if 'centro-login' in t:
        print('%s -> отдана форма входа (вход не состоялся)' % inn)
        continue
    imya = re.search(r'<h1[^>]*>(.{0,90}?)</h1>', t, re.S)
    print('%s http=%s знаков=%d | %s' % (inn, kod, len(t),
                                         re.sub(r'\s+', ' ', imya.group(1)).strip() if imya else '?'))
    print('   карточек факта ....... %d' % t.count('fact-card'))
    print('   снимков доказательств  %d' % t.count('/static/centro/dokaz/'))
    print('   ссылок на источники .. %d' % len(re.findall(r'href="https?://', t)))
    oboz = re.findall(r'class="tag[^"]*">([^<]{3,30})<', t)
    print('   метки на странице: %s' % ', '.join(list(dict.fromkeys(x.strip() for x in oboz))[:8]))
