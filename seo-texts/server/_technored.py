# -*- coding: utf-8 -*-
"""Технорэд: что за завод, где и когда. Плюс ИНН."""
import json, os, re, ssl, urllib.request

CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0', 'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}
try:
    r = НП.open(urllib.request.Request(
        'https://technored.ru/news/stroitelstvo-zavoda-technored/', headers=H), timeout=45)
    ч = re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ', re.sub(
        r'<script.*?</script>|<style.*?</style>',' ', r.read(400000).decode('utf-8','replace'), flags=re.S)))
    i = max(ч.find('завод'), 0)
    o['страница_технорэд'] = ч[i:i+1100]
except Exception as e:
    o['страница_технорэд'] = repr(e)[:90]

ТОК = os.environ.get('DADATA_TOKEN','')
for имя in ('ТЕХНОРЭД', 'Технорэд'):
    try:
        req = urllib.request.Request(
            'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
            data=json.dumps({'query': имя, 'count': 4}).encode(),
            headers={'Content-Type':'application/json','Accept':'application/json',
                     'Authorization':'Token '+ТОК})
        with urllib.request.urlopen(req, timeout=30) as rr:
            d = json.loads(rr.read())
        o['дадата_'+имя] = [{'имя': s.get('value'), 'инн': (s.get('data') or {}).get('inn'),
                             'статус': (((s.get('data') or {}).get('state') or {}).get('status')),
                             'регион': (((s.get('data') or {}).get('address') or {}).get('data') or {}).get('region_with_type'),
                             'оквэд': (s.get('data') or {}).get('okved')}
                            for s in (d.get('suggestions') or [])[:4]]
        break
    except Exception as e:
        o['дадата_'+имя] = repr(e)[:80]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:4800])
