# -*- coding: utf-8 -*-
"""Что реально лежит в найденных реестрах региональных фондов."""
import json
import re
import ssl
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))

адреса = [
    'https://frpnso.ru/vidanniy_crediti/',
    'https://frp62.ru/project',
    'https://smb35.ru/reestr',
    'https://fondsakha.ru/raskrytie-informatsii/reestr-poluchatelej-podderzhki',
    'https://invest.pskov.ru/rfrp/proekti/',
]
o = []
for u in адреса:
    зап = {'url': u}
    try:
        r = НП.open(urllib.request.Request(u, headers=H), timeout=35)
        h = r.read(500000).decode('utf-8', 'replace')
        зап['код'] = r.getcode()
    except urllib.error.HTTPError as e:
        зап['код'] = e.code
        h = ''
    except Exception as e:
        зап['код'] = repr(e)[:70]
        h = ''
    if h:
        т = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S)
        т = re.sub(r'<[^>]+>', ' ', т)
        т = re.sub(r'\s+', ' ', т)
        компании = sorted({m for m in re.findall(
            r'(?:ООО|АО|ПАО|ЗАО|ИП)\s*[«"]?[А-ЯЁ][^»"<]{2,45}[»"]?', т)})
        зап['компаний_видно'] = len(компании)
        зап['примеры'] = компании[:5]
        зап['ИНН_видно'] = len(set(re.findall(r'\b\d{10}\b|\b\d{12}\b', т)))
        зап['сумм_видно'] = len(re.findall(r'\d{1,4}[,.]?\d*\s*(?:млн|млрд|000\s*000)', т))
        зап['есть_таблица'] = '<table' in h.lower()
        зап['ссылки_на_файлы'] = sorted({
            m for m in re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|pdf))"', h, re.I)})[:3]
    o.append(зап)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
