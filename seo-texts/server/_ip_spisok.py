# -*- coding: utf-8 -*-
"""Что видно в отфильтрованной выборке investprojects: заголовки карточек и ID."""
import json
import re
import ssl
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
     'Accept-Language': 'ru,en;q=0.9',
     'Referer': 'https://investprojects.info/project-base'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))

URL = ('https://investprojects.info/project-base?locations=-208928,-208935,-2429801,'
       '-2429802,-2431974,-2438159,-2440668,-2444932,-2449969,-208976,-2864845,-2864846,'
       '-2864847,-2864848,-2864849,-2864850,-2864851,-2864852,-2864853,-2864854,-2864855,'
       '-2864856,-2864857,-2864858,-2864859,-2864860,-2864861,-2864862,-2864863,-2864864,'
       '-209005,-209065,-209070,-209076,-209079&stages=-25,-20,-21,-23,-22,-24'
       '&invest_range=50000000-19057614000000&page=3')

o = {}
try:
    r = НП.open(urllib.request.Request(URL, headers=H), timeout=60)
    html = r.read(900000).decode('utf-8', 'replace')
    o['код'] = r.getcode()
except urllib.error.HTTPError as e:
    o['код'] = e.code
    html = ''
except Exception as e:
    o['код'] = repr(e)[:90]
    html = ''
o['байт'] = len(html)

# Карточки: ссылка вида /project-base/NNNNNN и текст рядом.
карточки = []
for m in re.finditer(r'href="(/project-base/(\d+))"[^>]*>(.{0,200}?)</a>', html, re.S):
    подпись = re.sub(r'<[^>]+>|\s+', ' ', m.group(3)).strip()
    if подпись:
        карточки.append({'id': m.group(2), 'название': подпись[:120]})
видели = set()
уник = []
for к in карточки:
    if к['id'] in видели:
        continue
    видели.add(к['id'])
    уник.append(к)
o['карточек_на_странице'] = len(уник)
o['карточки'] = уник[:30]

ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
ч = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ч))
o['найдено_в_выборке'] = (re.search(r'(Найдено|Всего)[^.]{0,60}', ч) or ['', ''])[0][:80]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5200])
