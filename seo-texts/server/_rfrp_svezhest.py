# -*- coding: utf-8 -*-
"""Есть ли у проектов регфондов даты и суммы — от этого зависит вся ценность."""
import json
import re
import ssl
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}

for url in ('https://frp62.ru/project', 'https://frpperm.ru/projects/',
            'https://rfrp36.govvrn.ru/projects/', 'https://frp74.ru/proekty/'):
    try:
        r = НП.open(urllib.request.Request(url, headers=H), timeout=35)
        сырое = r.read(800000)
        код = r.getcode()
    except Exception as e:
        o[url] = repr(e)[:70]
        continue
    т = сырое.decode('utf-8', 'replace')
    if 'charset=windows-1251' in т[:900].lower():
        т = сырое.decode('cp1251', 'replace')
    ч = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(
        r'<script.*?</script>|<style.*?</style>', ' ', т, flags=re.S)))
    o[url] = {
        'код': код,
        'годы': sorted(set(re.findall(r'\b20(?:1[5-9]|2[0-9])\b', ч)))[-6:],
        'сумм_млн': len(re.findall(r'\d{1,4}[,.]?\d*\s*млн', ч)),
        'примеры_сумм': re.findall(r'\d{1,4}[,.]?\d*\s*(?:млн|млрд)[^.,;]{0,25}', ч)[:4],
        'есть_пагинация': bool(re.search(r'PAGEN|page=\d|\?page|pagination', т, re.I)),
        'кусок': ч[ч.find('ООО') - 120:ч.find('ООО') + 260].strip()[:330] if 'ООО' in ч else ч[:200],
    }
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])
