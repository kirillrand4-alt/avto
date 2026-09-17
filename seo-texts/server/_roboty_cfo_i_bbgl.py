# -*- coding: utf-8 -*-
"""Завод роботов в ЦФО + что реально отдаёт bbgl.ru без входа."""
import json, os, re, ssl, urllib.parse, urllib.request

CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0', 'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
U = os.environ.get('XMLRIVER_USER',''); K = os.environ.get('XMLRIVER_KEY','')
o = {}

def искать(q, движок='google', n=6):
    база = ('http://xmlriver.com/search/xml' if движок=='yandex'
            else 'http://xmlriver.com/search_google/xml')
    try:
        with НП.open('%s?user=%s&key=%s&query=%s&groupby=%d' % (
                база, U, K, urllib.parse.quote(q), n), timeout=90) as r:
            xml = r.read(400000).decode('utf-8','replace')
    except Exception as e:
        return ['ОШИБКА %r' % (e,)]
    ч = lambda s: re.sub(r'\s+',' ', re.sub(r'<[^>]+>','',s)).strip()
    out=[]
    for б in re.findall(r'<doc>(.*?)</doc>', xml, re.S)[:n]:
        out.append({'з': ч((re.search(r'<title>(.*?)</title>',б,re.S) or ['',''])[1])[:100],
                    'т': ч((re.search(r'<passage>(.*?)</passage>',б,re.S) or ['',''])[1])[:200],
                    'u': ч((re.search(r'<url>(.*?)</url>',б,re.S) or ['',''])[1])[:70]})
    return out

o['роботы_ЦФО'] = искать('создание производства промышленных роботов 2025 завод '
                          'Московская Тульская Калужская Липецкая Рязанская область')
o['роботы_ЦФО_2'] = искать('"производство промышленных роботов" новый завод 2025 '
                            'запуск ЦФО инвестиции', движок='yandex')

# bbgl: полный текст карточки
try:
    r = НП.open(urllib.request.Request('https://bbgl.ru/prjcts/17003', headers=H), timeout=45)
    html = r.read(400000).decode('utf-8','replace')
    ч2 = re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ', re.sub(
        r'<script.*?</script>|<style.*?</style>',' ', html, flags=re.S)))
    i = ч2.find('Строительство завода по производству промышленных роботов в Самарской об', 2000)
    o['bbgl_карточка'] = ч2[i:i+1500] if i>0 else ч2[3000:4500]
except Exception as e:
    o['bbgl_карточка'] = repr(e)[:80]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5400])
