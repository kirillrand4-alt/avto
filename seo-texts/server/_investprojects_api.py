# -*- coding: utf-8 -*-
"""Официальный путь: что за API у investprojects и почём доступ."""
import json, re, ssl, urllib.error, urllib.request

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0', 'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}

def взять(u, лимит=400000):
    try:
        r = НП.open(urllib.request.Request(u, headers=H), timeout=40)
        return r.getcode(), r.read(лимит).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, (e.read(400) or b'').decode('utf-8', 'replace')
    except Exception as e:
        return -1, repr(e)[:90]

def плоско(h):
    ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ч))

# Ищем страницу про API в меню.
код, html = взять('https://investprojects.info/tariffs')
ч = плоско(html)
i = ч.lower().find('тариф')
o['тарифы_текст'] = ч[i:i + 1400] if i > 0 else ч[:1000]
o['цены_на_странице'] = re.findall(r'\d[\d\s]{2,9}\s*(?:₽|руб|рублей)', ч)[:12]
ссылки = sorted(set(re.findall(r'href="(/[^"#?]{2,40})"', html)))
o['ссылки_меню'] = [s for s in ссылки if re.search(r'api|tarif|price|podpis', s, re.I)][:10]

for путь in ('/api', '/about-api', '/api-program', '/programma-api'):
    код2, h2 = взять('https://investprojects.info' + путь, 200000)
    if код2 == 200:
        ч2 = плоско(h2)
        o['страница_api'] = {'путь': путь, 'текст': ч2[:1200]}
        break
    o.setdefault('пробы_api', {})[путь] = код2
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])
