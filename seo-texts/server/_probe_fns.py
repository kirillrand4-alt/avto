# -*- coding: utf-8 -*-
import json, sys, urllib.request
sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC
o = {}
tok = EC._read_secret('DADATA_TOKEN')
body = json.dumps({'query': '5032111150'}).encode()
req = urllib.request.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party', data=body, method='POST',
                             headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Token ' + tok})
d = json.loads(urllib.request.urlopen(req, timeout=30).read())['suggestions'][0]['data']
o['dadata_keys'] = sorted(d.keys())
o['okved'] = d.get('okved'); o['okveds'] = (d.get('okveds') or [])[:3]; o['finance'] = d.get('finance')
o['address_region'] = ((d.get('address') or {}).get('data') or {}).get('region_with_type')
for url in ('https://bo.nalog.ru/advanced-search/organizations/search?query=5032111150&page=0',
            'https://bo.nalog.ru/nbo/organizations/search?query=5032111150&page=0'):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}), timeout=30)
        o[url[-60:]] = r.read()[:700].decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        o[url[-60:]] = repr(e)[:150]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1, default=str)[:4000])
