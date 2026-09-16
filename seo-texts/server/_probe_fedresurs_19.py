# -*- coding: utf-8 -*-
"""Проба 19: точный счёт типов в справочнике (для документа)."""
import io, sys, json, ssl
import urllib.request, urllib.error
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'
r = OP.open(urllib.request.Request('https://fedresurs.ru/backend/reference-book/message-types',
                                   headers={'User-Agent': UA, 'Accept': '*/*',
                                            'Referer': 'https://fedresurs.ru/'}), timeout=45)
d = json.loads(r.read().decode('utf-8', 'replace'))
print('всего записей в справочнике: %d' % len(d))
print('по project: %s' % dict(Counter(x.get('project') for x in d)))
print('из них isOld=True: %d' % sum(1 for x in d if x.get('isOld')))
print('уникальных названий: %d' % len({(x.get('name') or '').strip().lower() for x in d}))
nb = [x for x in d if x.get('project') != 1]
print('НЕ банкротных (project!=1): %d, из них действующих: %d'
      % (len(nb), sum(1 for x in nb if not x.get('isOld'))))
print('банкротных (project==1): %d' % sum(1 for x in d if x.get('project') == 1))
print('слово «намерен» в названиях:')
for x in d:
    if 'намерен' in (x.get('name') or '').lower():
        print('   %-52s %s' % (x.get('code'), x.get('name')[:110]))
print('\n==== КОНЕЦ ПРОБЫ 19 ====')
