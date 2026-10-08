# -*- coding: utf-8 -*-
"""Проверка листания xmlriver: page=0 — это первая страница или вторая? Плюс баланс."""
import os
import re
import urllib.parse
import urllib.request

U, K = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def урлы(движок, q, стр=None):
    u = 'http://xmlriver.com/search_%s/xml?user=%s&key=%s&query=%s' % (движок, U, K, urllib.parse.quote(q))
    if стр is not None:
        u += '&page=%d' % стр
    for _ in range(3):
        x = НП.open(u, timeout=120).read(3000000).decode('utf-8', 'replace')
        if 'перезапрос' not in x:
            break
    return [re.sub(r'^https?://(www\.)?', '', a).rstrip('/') for a in re.findall(r'<url>(.*?)</url>', x, re.S)]


for движок in ('yandex', 'google'):
    for q in ('элеватор Краснодарский край', 'рисозавод Краснодарский край'):
        д = урлы(движок, q)
        с = {п: урлы(движок, q, п) for п in (0, 1, 2, 3)}
        print(движок, q, 'без page: %d' % len(д))
        for п, л in с.items():
            print('  page=%d: %d доков, общих с «без page» %d, с page=0 %d' % (
                п, len(л), len(set(л) & set(д)), len(set(л) & set(с[0]))))
for путь in ('http://xmlriver.com/api/get_balance/?user=%s&key=%s', 'http://xmlriver.com/api/get_balance/yandex/?user=%s&key=%s'):
    try:
        print('баланс', путь.split('/api/')[1].split('?')[0], НП.open(путь % (U, K), timeout=30).read(300).decode('utf-8', 'replace'))
    except Exception as e:  # noqa: BLE001
        print('баланс ошибка', repr(e)[:80])
