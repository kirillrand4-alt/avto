# -*- coding: utf-8 -*-
"""Проверка страниц панели НА СЕРВЕРЕ, с настоящим входом.

Первый заход этой пробы вернул 200 у обеих страниц — и это ничего не значило: под
двухсоткой была форма входа. Поэтому проба теперь логинится (user3, пароль лежит в
C:\\sender\\centro-user3.txt) и смотрит не код ответа, а содержимое: есть ли колонки
«Выручка» и «ОКВЭД», сколько строк в таблице, сколько предприятий в своде.
"""
import json, os, re, urllib.request, urllib.parse, http.cookiejar

B = 'http://127.0.0.1:8012/obzvon'
PW = ''
put_pw = r'C:\sender\centro-user3.txt'
if os.path.exists(put_pw):
    t = open(put_pw, encoding='utf-8', errors='replace').read()
    m = re.search(r'(?:пароль|password)\s*[:=]\s*(\S+)', t, re.I)
    PW = m.group(1) if m else t.strip().split()[-1]

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
o = {'парольНайден': bool(PW)}
try:
    d = urllib.parse.urlencode({'username': 'user3', 'password': PW}).encode()
    r = op.open(urllib.request.Request(B + '/centro/login', data=d), timeout=40)
    o['вход'] = r.status
    o['куки'] = len(cj)
except Exception as e:
    o['вход'] = str(e)[:150]

for p in ('/centro/park', '/centro/park?sort=vyruchka&est_vyruchka=1',
          '/centro/park?okved=28', '/centro/spisok',
          '/centro/park/7736050003'):   # карточка, которую показал владелец
    try:
        r = op.open(B + p, timeout=90)
        t = r.read().decode('utf-8', 'replace')
        z = {'http': r.status, 'знаков': len(t), 'форма входа': 'name="password"' in t,
             'есть Выручка': 'Выручка' in t, 'есть ОКВЭД': 'ОКВЭД' in t,
             'строк таблицы': t.count('<tr>') - 1,
             'centro.css': 'centro.css' in t,
             # разметка панели, а не своя: по этим классам видно, что вид тот же
             'company-hero': 'company-hero' in t, 'contacts-grid': 'contacts-grid' in t,
             'data-list': 'data-list' in t, 'topbar': 'class="topbar"' in t,
             'свой старый CSS': 'font:14px/1.5' in t,
             'деньги «млн» подряд': 'млн ₽' in t and '000 млн' in t}
        m = re.search(r'выручка[^<]*</dt><dd>([^<]{0,40})', t, re.I)
        if m:
            z['выручка в карточке'] = m.group(1).strip()
        m = re.search(r'<b>([\d\s ]{1,9})</b><span>предприятий', t)
        if m:
            z['предприятий в своде'] = m.group(1).strip()
        m = re.search(r'<b>([\d\s ]{1,9})</b><span>с выручкой', t)
        if m:
            z['с выручкой'] = m.group(1).strip()
        o[p] = z
    except Exception as e:
        o[p] = {'ошибка': str(e)[:170]}
print(json.dumps(o, ensure_ascii=False, indent=1))
