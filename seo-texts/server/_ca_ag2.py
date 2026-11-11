import os, urllib.request
П = r'C:\sender\server\ca'
for и in ('sol', 'luna'):
    л = os.path.join(П, 'ca_agenty_dosyl_%s.log' % и)
    if os.path.exists(л):
        print('===ИТОГ===' if и == 'sol' else '', и, open(л, encoding='utf-8', errors='replace').read()[-260:].replace('\n', ' | '))
try:
    б = urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')), timeout=30).read(100)
    print('баланс xmlriver', б)
except Exception as e:
    print('баланс', repr(e)[:80])
