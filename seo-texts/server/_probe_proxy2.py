# -*- coding: utf-8 -*-
import json, re, urllib.request, urllib.parse, urllib.error, time
import socks, sockshandler
прокси = json.load(open(r'C:\sender\server\checko-proxies.json'))
п = прокси[0]
u = urllib.parse.urlsplit(п['proxy'])
op = urllib.request.build_opener(sockshandler.SocksiPyHandler(socks.SOCKS5, u.hostname, u.port, True, u.username, u.password))
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
     'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
     'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8', 'Upgrade-Insecure-Requests': '1', 'Sec-Fetch-Dest': 'document',
     'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'none', 'Sec-Fetch-User': '?1'}
o = {}
def get(url):
    try:
        r = op.open(urllib.request.Request(url, headers=H), timeout=40)
        return r.status, dict(r.headers), r.read()[:3000].decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()[:3000].decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return 'ERR', {}, repr(e)[:200]
for url in ('https://checko.ru/', 'https://checko.ru/company/1135032003506/activity'):
    код, хед, тело = get(url)
    o[url] = {'код': код, 'заголовки': {k: v for k, v in хед.items() if k.lower() in ('server', 'retry-after', 'set-cookie', 'content-type', 'x-ratelimit-remaining', 'cf-ray')},
              'тело': re.sub(r'\s+', ' ', re.sub(r'<script.*?</script>', ' ', тело, flags=re.S))[:600]}
# ротация IP первого прокси и повтор
try:
    o['ротация'] = urllib.request.urlopen(п['rotate'], timeout=40).read()[:200].decode('utf-8', 'replace')
except Exception as e:  # noqa: BLE001
    o['ротация'] = repr(e)[:150]
time.sleep(15)
код, хед, тело = get('https://checko.ru/company/1135032003506/activity')
o['после_ротации'] = {'код': код, 'тело': re.sub(r'\s+', ' ', тело)[:300]}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])
