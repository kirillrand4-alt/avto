# -*- coding: utf-8 -*-
import json, os, re, time, urllib.parse, urllib.request
U = os.environ.get('XMLRIVER_USER', ''); K = os.environ.get('XMLRIVER_KEY', '')
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(u, n=600000):
    with НП.open(u, timeout=90) as r:
        return r.read(n).decode('utf-8', 'replace')
o = {'время': time.strftime('%Y-%m-%d %H:%M'), 'баланс': get('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (U, K), 80)}
for g in (10, 50, 100):
    t = time.time()
    x = get('http://xmlriver.com/search_yandex/xml?user=%s&key=%s&query=%s&groupby=%d' % (U, K, urllib.parse.quote('молокозавод Курская область'), g))
    urls = re.findall(r'<url>(.*?)</url>', x)
    o['g%d' % g] = {'сек': round(time.time() - t), 'docs': len(re.findall(r'<doc>', x)), 'urls': [re.sub(r'^https?://', '', u)[:40] for u in urls[:60]], 'err': (re.search(r'<error[^>]*>(.*?)</error>', x) or [None, ''])[1][:80]}
o['баланс_после'] = get('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (U, K), 80)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False)[:5800])
