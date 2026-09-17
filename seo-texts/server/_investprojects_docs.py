# -*- coding: utf-8 -*-
"""Документация API investprojects: какие поля и методы обещают."""
import json, re, ssl, urllib.error, urllib.request

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0', 'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    r = НП.open(urllib.request.Request('https://investprojects.info/docs/api', headers=H), timeout=40)
    код, html = r.getcode(), r.read(500000).decode('utf-8', 'replace')
except urllib.error.HTTPError as e:
    код, html = e.code, ''
except Exception as e:
    код, html = -1, repr(e)[:80]
ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
ч = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ч))
i = ч.find('API')
print('===ИТОГ===')
print(json.dumps({'код': код, 'байт': len(html),
                  'текст': ч[i:i + 2200] if i > 0 else ч[:1500],
                  'методы': sorted(set(re.findall(r'/api/[a-zA-Z0-9/_\-]{2,40}', html)))[:20]},
                 ensure_ascii=False, indent=1)[:5000])
