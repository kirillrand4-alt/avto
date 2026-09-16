# -*- coding: utf-8 -*-
"""Проба 20: точное число путей в OpenAPI (для документа)."""
import io, sys, json, ssl
import urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
C = ssl.create_default_context(); C.check_hostname = False; C.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=C))
r = OP.open(urllib.request.Request(
    'https://fedresurs.ru/backend/swagger/v1/swagger.json',
    headers={'User-Agent': 'Mozilla/5.0 Chrome/126.0', 'Referer': 'https://fedresurs.ru/'}), timeout=60)
b = r.read()
sw = json.loads(b.decode('utf-8', 'replace'))
ops = sum(len([m for m in v if m in ('get', 'post', 'put', 'delete')]) for v in sw['paths'].values())
print('размер swagger.json: %d байт' % len(b))
print('версия OpenAPI: %s, title: %s' % (sw.get('openapi'), (sw.get('info') or {}).get('title')))
print('ПУТЕЙ: %d, ОПЕРАЦИЙ: %d, схем: %d'
      % (len(sw['paths']), ops, len((sw.get('components') or {}).get('schemas') or {})))
