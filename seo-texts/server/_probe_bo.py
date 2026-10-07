# -*- coding: utf-8 -*-
import json, urllib.request
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36', 'Accept': 'application/json, text/plain, */*'}
o = {}
def get(u):
    try:
        r = op.open(urllib.request.Request(u, headers=H), timeout=30)
        return r.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return 'ERR ' + repr(e)[:150]
s = get('https://bo.nalog.ru/nbo/organizations/search?query=5032111150&page=0')
o['search'] = s[:600]
try:
    j = json.loads(s)
    cont = j.get('content') or []
    oid = cont[0]['id'] if cont else None
    o['id'] = oid
    if oid:
        b = get('https://bo.nalog.ru/nbo/organizations/%s/bfo/' % oid)
        o['bfo'] = b[:600]
        jb = json.loads(b)
        if jb:
            last = sorted(jb, key=lambda x: x.get('period', ''))[-1]
            o['last_period'] = last.get('period')
            det = get('https://bo.nalog.ru/nbo/bfo/%s/details' % last['id'])
            o['details'] = det[:1500]
except Exception as e:  # noqa: BLE001
    o['parse'] = repr(e)[:200]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])
