# -*- coding: utf-8 -*-
"""Воспроизводим переход «список -> карточка» настоящим входом и смотрим ответ.

Проверяем три случая, чтобы понять правило, а не угадать его:
  1) компания, назначенная ЭТОМУ пользователю;
  2) спорная компания владельца (назначена user1);
  3) она же со сбросом фильтров.
"""
import json, os, re, sqlite3, urllib.parse, urllib.request, http.cookiejar

B = 'http://127.0.0.1:8012/obzvon'
SP = r'C:\seostat\data\centro_sales.db'
PW = ''
if os.path.exists(r'C:\sender\centro-user3.txt'):
    t = open(r'C:\sender\centro-user3.txt', encoding='utf-8', errors='replace').read()
    m = re.search(r'(?:пароль|password)\s*[:=]\s*(\S+)', t, re.I)
    PW = m.group(1) if m else t.strip().split()[-1]

s = sqlite3.connect('file:%s?mode=ro' % SP, uri=True)
moy = s.execute("select inn from company_assignment where username='user3' and inn not in "
                "(select inn from hidden_item where kind='company') limit 1").fetchone()
s.close()
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open(B + '/centro/login', timeout=30)
op.open(urllib.request.Request(B + '/centro/login', data=urllib.parse.urlencode(
    {'username': 'user3', 'password': PW}).encode()), timeout=40)

o = {'вошли_как': 'user3', 'мой_инн': moy[0] if moy else ''}
for imya, put in (('своя компания', '/centro?inn=%s' % (moy[0] if moy else '')),
                  ('чужая (user1) 5103070023', '/centro?inn=5103070023'),
                  ('чужая, из списка', '/centro/spisok?q=5103070023')):
    try:
        with op.open(B + put, timeout=90) as r:
            body = r.read().decode('utf-8', 'replace')
        o[imya] = {'http': r.status, 'знаков': len(body),
                   'это ошибка JSON': body.strip().startswith('{"detail"')}
    except urllib.error.HTTPError as e:
        o[imya] = {'http': e.code, 'тело': e.read().decode('utf-8', 'replace')[:120]}
    except Exception as e:
        o[imya] = str(e)[:120]
print(json.dumps(o, ensure_ascii=False, indent=1))
