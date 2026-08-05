# -*- coding: utf-8 -*-
"""Видна ли «Дубль» на странице очередей под проверенным входом user3.

Секрет у служб РАЗНЫЙ: прошлый прогон брал его из первой попавшейся и потому
не вошёл никуда. Беру пароль, уже проверенный против bcrypt-хэша.
"""
import base64, http.cookiejar, re, urllib.parse, urllib.request
цепь = base64.b64encode(b'admin:Vn0XDmyRZ1yQ').decode()
банка = http.cookiejar.CookieJar()
от = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(банка))
д = urllib.parse.urlencode({'login': 'user3', 'username': 'user3',
                            'password': '2c8029175b9bd5b26629fef8b08dcb04'}).encode()
з = urllib.request.Request('http://127.0.0.1:8014/p25/centro/login', data=д,
                           headers={'Authorization': 'Basic ' + цепь,
                                    'Content-Type': 'application/x-www-form-urlencoded'})
т = от.open(з, timeout=25).read(400000).decode('utf-8', 'replace')
print('вошёл:', 'Неверный логин' not in т, '| кука:', [c.name for c in банка])
з2 = urllib.request.Request('http://127.0.0.1:8014/p25/centro',
                            headers={'Authorization': 'Basic ' + цепь})
т2 = от.open(з2, timeout=25).read(500000).decode('utf-8', 'replace')
print('«Дубль» на странице:', 'Дубль' in т2)
print('ссылка call_status=dubl:', 'call_status=dubl' in т2)
print('очереди, найденные на странице:')
for м in re.finditer(r'call_status=([a-z_]+)"[^>]*>([^<]{0,40})', т2):
    print(f'   {м.group(1):16} {м.group(2).strip()}')
