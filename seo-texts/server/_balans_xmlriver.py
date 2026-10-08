import json, os, urllib.request
U, K = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
print('===ИТОГ==='); print(json.dumps({'баланс': op.open('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (U, K), timeout=30).read(100).decode()}))
