# -*- coding: utf-8 -*-
"""Кладёт centro.html в панель обзвона — с копией и с проверкой, что страница жива.

Это ГЛАВНАЯ рабочая страница владельца, поэтому: копия перед заменой, затем запрос к
странице и проверка, что новые ссылки в теле есть, а старые пункты не пропали. Если
что-то не так — сразу возвращаем копию, не оставляя панель сломанной.
"""
import json, os, re, shutil, time, urllib.request, urllib.parse, http.cookiejar

IST = r'C:\sender\_ops\centro.html'
CEL = r'C:\seostat\app\templates\centro.html'
B = 'http://127.0.0.1:8012/obzvon'
o = {}
bak = CEL + '.bak-%d' % int(time.time())
shutil.copyfile(CEL, bak)
o['kopiya'] = os.path.basename(bak)
shutil.copyfile(IST, CEL)
o['polozheno'] = os.path.getsize(CEL)

PW = ''
if os.path.exists(r'C:\sender\centro-user3.txt'):
    t = open(r'C:\sender\centro-user3.txt', encoding='utf-8', errors='replace').read()
    m = re.search(r'(?:пароль|password)\s*[:=]\s*(\S+)', t, re.I)
    PW = m.group(1) if m else t.strip().split()[-1]
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:
    op.open(B + '/centro/login', timeout=30)
    op.open(urllib.request.Request(
        B + '/centro/login',
        data=urllib.parse.urlencode({'username': 'user3', 'password': PW}).encode()), timeout=40)
    with op.open(B + '/centro', timeout=90) as r:
        s = r.read().decode('utf-8', 'replace')
    o['centro'] = {'http': r.status, 'знаков': len(s),
                   'ссылка на список': '/centro/spisok' in s,
                   'ссылка на парк': '/centro/park' in s,
                   'старые пункты целы': all(x in s for x in
                       ('Вся очередь', 'Взял в работу', 'Дубль'))}
    if not (o['centro']['ссылка на список'] and o['centro']['старые пункты целы']):
        shutil.copyfile(bak, CEL)
        o['ОТКАТ'] = 'страница без новых ссылок или без старых пунктов — вернул копию'
except Exception as e:
    shutil.copyfile(bak, CEL)
    o['ОТКАТ'] = 'страница не открылась: %s' % str(e)[:120]
print(json.dumps(o, ensure_ascii=False, indent=1))
