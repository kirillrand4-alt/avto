# -*- coding: utf-8 -*-
import json, re, urllib.request, urllib.parse, urllib.error
import socks, sockshandler
прокси = json.load(open(r'C:\sender\server\checko-proxies.json'))
u = urllib.parse.urlsplit(прокси[1]['proxy'])
op = urllib.request.build_opener(sockshandler.SocksiPyHandler(socks.SOCKS5, u.hostname, u.port, True, u.username, u.password))
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
     'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
     'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8', 'Upgrade-Insecure-Requests': '1', 'Sec-Fetch-Dest': 'document',
     'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'none', 'Sec-Fetch-User': '?1'}
o = {}
def get(url):
    try:
        r = op.open(urllib.request.Request(url, headers=H), timeout=40)
        return r.status, r.geturl(), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, url, e.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return 'ERR', url, repr(e)[:200]
код, урл, html = get('https://checko.ru/search?query=5032111150')
o['search'] = {'код': код, 'итоговый_url': урл}
ссылки = sorted(set(re.findall(r'href="(/company/[^"#?]+)', html)))[:15]
o['ссылки_company'] = ссылки
if код == 200 and '/company/' in урл:
    комп = урл
else:
    комп = 'https://checko.ru' + ссылки[0] if ссылки else ''
if комп:
    код2, урл2, h2 = get(комп)
    o['company'] = {'код': код2, 'url': урл2}
    т = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<script.*?</script>', ' ', h2, flags=re.S)))
    for слово in ('ОКВЭД', 'Виды деятельности', 'Основной вид', 'Выручка'):
        i = т.find(слово)
        o['фрагмент_' + слово] = т[i:i + 300] if i >= 0 else 'нет'
    o['ссылки_на_странице'] = sorted(set(x for x in re.findall(r'href="([^"]+)"', h2) if 'activ' in x or 'okved' in x or 'finan' in x))[:10]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])
