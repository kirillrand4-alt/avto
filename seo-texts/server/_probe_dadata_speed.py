# -*- coding: utf-8 -*-
import json, sys, time, urllib.request
sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC
tok = EC._read_secret('DADATA_TOKEN')
o = []
for имя, op in (('прямой', urllib.request.build_opener(urllib.request.ProxyHandler({}))), ('по умолчанию', urllib.request.build_opener())):
    for инн in ('7707083893', '5045016560', '7724766868'):
        t = time.time()
        try:
            req = urllib.request.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                                         data=json.dumps({'query': инн}).encode(), method='POST', headers={
                                             'Content-Type': 'application/json', 'Accept': 'application/json',
                                             'Authorization': 'Token ' + tok})
            r = op.open(req, timeout=30)
            с = json.loads(r.read()).get('suggestions') or []
            o.append([имя, инн, r.status, (с[0]['data'].get('okved') if с else None), round(time.time() - t, 1)])
        except Exception as e:
            o.append([имя, инн, repr(e)[:90], round(time.time() - t, 1)])
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False))
