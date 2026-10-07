# -*- coding: utf-8 -*-
import json, re, sys, time, urllib.request, urllib.parse
o = {}
try:
    import socks, sockshandler  # PySocks
    o['pysocks'] = 'есть'
except ImportError as e:
    o['pysocks'] = 'нет: ' + str(e)
    print('===ИТОГ===')
    print(json.dumps(o, ensure_ascii=False))
    sys.exit(0)
прокси = json.load(open(r'C:\sender\server\checko-proxies.json'))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
for k, п in enumerate(прокси):
    u = urllib.parse.urlsplit(п['proxy'])
    op = urllib.request.build_opener(sockshandler.SocksiPyHandler(socks.SOCKS5, u.hostname, u.port, True, u.username, u.password))
    з = {}
    try:
        з['ip'] = op.open(urllib.request.Request('https://api.ipify.org', headers={'User-Agent': UA}), timeout=30).read().decode()[:40]
    except Exception as e:  # noqa: BLE001
        з['ip'] = 'ERR ' + repr(e)[:100]
    try:
        r = op.open(urllib.request.Request('https://checko.ru/company/1135032003506/activity', headers={'User-Agent': UA, 'Accept-Language': 'ru'}), timeout=40)
        h = r.read().decode('utf-8', 'replace')
        t = re.sub(r'<[^>]+>', ' ', h)
        m = re.search(r'(Виды\s+деятельности|ОКВЭД)', t)
        з['checko'] = 'ok %d байт, кодов %d' % (len(h), len(re.findall(r'\b\d{2}\.\d{1,2}(?:\.\d{1,2})?\b', t[m.start():] if m else '')))
    except Exception as e:  # noqa: BLE001
        з['checko'] = 'ERR ' + repr(e)[:120]
    o['прокси_%d' % (k + 1)] = з
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
