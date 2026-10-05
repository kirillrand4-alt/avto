# -*- coding: utf-8 -*-
"""Баланс XMLRiver (печатает только ответ сервиса, ключ вырезается)."""
import os, urllib.parse, urllib.request
u, k = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
q = urllib.parse.urlencode({'user': u, 'key': k})
print('===ИТОГ===')
for path in ('api/get_balance/', 'api/get_balance/yandex/', 'api/get_cost/yandex/', 'api/get_cost/google/'):
    try:
        t = urllib.request.urlopen('http://xmlriver.com/%s?%s' % (path, q), timeout=30).read()[:300]
        t = t.decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        t = type(e).__name__ + ' ' + str(e)[:100]
    print(path, '->', t.replace(k, '***') if k else t)
