# -*- coding: utf-8 -*-
"""Истории успеха ФРП + поиск API за заглушкой ГИСП."""
import json
import re
import ssl
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru', 'Accept': 'text/html,application/json,*/*'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}


def взять(url, лимит=None, tmo=45):
    try:
        r = НП.open(urllib.request.Request(url, headers=H), timeout=tmo)
        т = (r.read(лимит) if лимит else r.read())
        return r.getcode(), т.decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, (e.read(300) or b'').decode('utf-8', 'replace')
    except Exception as e:
        return -1, repr(e)[:120]


# --- 1. Истории успеха: сколько их и что в карточке.
код, html = взять('https://frprf.ru/istorii-uspekha/')
ид = sorted(set(re.findall(r'/istorii-uspekha/(\d+)/', html)))
o['истории_успеха'] = {'код': код, 'ссылок_на_странице': len(ид)}
for стр in (2, 3, 10):
    к2, h2 = взять('https://frprf.ru/istorii-uspekha/?PAGEN_1=%d' % стр, 200000)
    и2 = set(re.findall(r'/istorii-uspekha/(\d+)/', h2))
    o['истории_успеха']['страница_%d' % стр] = {'код': к2, 'карточек': len(и2),
                                                'новых': len(и2 - set(ид))}
    ид = sorted(set(ид) | и2)
o['истории_успеха']['всего_собрано_ид'] = len(ид)

if ид:
    к3, карточка = взять('https://frprf.ru/istorii-uspekha/%s/' % ид[-1], 200000)
    чист = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', карточка, flags=re.S)
    чист = re.sub(r'<[^>]+>', ' ', чист)
    чист = re.sub(r'\s+', ' ', чист)
    хвост = чист[чист.find('Истории успеха') + 400:][:700] if 'Истории успеха' in чист else чист[:700]
    o['истории_успеха']['образец_карточки'] = {'id': ид[-1], 'текст': хвост}

# --- 2. ГИСП: ищем API за заглушкой.
код, html = взять('https://gisp.gov.ru/', 300000)
o['гисп_главная'] = {'код': код, 'байт': len(html)}
скрипты = sorted(set(re.findall(r'(?:src|href)="([^"]+\.js)"', html)))[:8]
o['гисп_скрипты'] = скрипты
адреса = set()
for s in скрипты[:6]:
    u = s if s.startswith('http') else 'https://gisp.gov.ru/' + s.lstrip('/')
    к, т = взять(u, 400000)
    if к != 200:
        continue
    for m in re.findall(r'["\'](/[a-zA-Z0-9/_\-]{4,60}(?:/api/|/rest/|\.json|/list|/search))["\']', т):
        адреса.add(m)
    for m in re.findall(r'["\'](https?://[a-z0-9.\-]*gisp[^"\']{0,60})["\']', т):
        адреса.add(m)
o['гисп_адреса_в_бандлах'] = sorted(адреса)[:25]

# Прямые пробы известных у таких порталов ручек.
пробы = {}
for u in ('https://gisp.gov.ru/api/', 'https://gisp.gov.ru/opendata/',
          'https://gisp.gov.ru/pp719v2/p/api/', 'https://gisp.gov.ru/frp/',
          'https://gisp.gov.ru/support-measures/', 'https://gisp.gov.ru/nppa/p/api/',
          'https://gisp.gov.ru/plp/p/api/'):
    к, т = взять(u, 300)
    пробы[u] = {'код': к, 'начало': т.replace('\n', ' ')[:110]}
o['гисп_пробы'] = пробы
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
