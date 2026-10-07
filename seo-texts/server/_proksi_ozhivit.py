# -*- coding: utf-8 -*-
import json, sys, time, urllib.request, urllib.parse
sys.path.insert(0, r'C:\sender\server')
import cc_checko_proxy as CP
o = []
for n, x in enumerate(json.load(open(r'C:\sender\server\checko-proxies.json'))):
    п = CP.Прокси(x)
    хост = urllib.parse.urlsplit(x['proxy']).hostname  # только хост, без логина/пароля
    t = time.time()
    код, _ = п.get('https://checko.ru/')
    з = {'n': n, 'хост': хост, 'до': код, 'сек': round(time.time() - t)}
    if код != 200:
        try:
            urllib.request.urlopen(x['rotate'], timeout=40).read()
            з['ротация'] = 'ok'
        except Exception as e:
            з['ротация'] = repr(e)[:60]
        time.sleep(25)
        з['после'] = п.get('https://checko.ru/')[0]
    o.append(з)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False))
