# -*- coding: utf-8 -*-
"""Все API-адреса и «денежные» слова внутри бандлов портала ЕГРЗ."""
import json
import re
import ssl
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0'}
o = {}
адреса = set()
денежные = set()

for имя in ('main.bundle.js', 'vendor.bundle.js', 'scripts.bundle.js'):
    try:
        req = urllib.request.Request('https://egrz.ru/' + имя, headers=H)
        with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
            т = r.read().decode('utf-8', 'replace')
        o.setdefault('бандлы', {})[имя] = len(т)
    except Exception as e:
        o.setdefault('бандлы', {})[имя] = 'ОШИБКА: %r' % (e,)
        continue
    for m in re.findall(r'["\'](https?://[a-zA-Z0-9.\-]+[^"\']{0,60})["\']', т):
        адреса.add(m[:100])
    for m in re.findall(r'["\']([A-Za-z_]*(?:API|Api|api)[A-Za-z_]*)["\']\s*[:,]', т):
        адреса.add('ключ:' + m)
    for m in re.findall(r'[A-Za-z]*(?:Cost|Price|Smeta|Sum)[A-Za-z]*', т):
        денежные.add(m)
    for m in re.findall(r'[Сс]метн\w*|[Сс]тоимост\w*|ТЭП|технико-экономическ\w*', т):
        денежные.add(m)

o['адреса'] = sorted(a for a in адреса if 'egrz' in a.lower() or a.startswith('ключ:'))[:40]
o['денежные_слова'] = sorted(денежные)[:40]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
