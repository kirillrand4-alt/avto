# -*- coding: utf-8 -*-
"""Куда ведут 307 у ГИСП и где сайты региональных фондов (РФРП)."""
import json
import re
import ssl
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru', 'Accept': '*/*'}


class БезРедиректов(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
БЕЗ = urllib.request.build_opener(urllib.request.ProxyHandler({}), БезРедиректов)
o = {}


def взять(url, лимит=None, редиректы=True, tmo=40):
    оп = НП if редиректы else БЕЗ
    try:
        r = оп.open(urllib.request.Request(url, headers=H), timeout=tmo)
        т = (r.read(лимит) if лимит else r.read())
        return r.getcode(), dict(r.headers), т.decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), (e.read(200) or b'').decode('utf-8', 'replace')
    except Exception as e:
        return -1, {}, repr(e)[:120]


# 1. Куда редиректят «апишные» пути ГИСП.
редиректы = {}
for u in ('https://gisp.gov.ru/pp719v2/p/api/', 'https://gisp.gov.ru/nppa/p/api/',
          'https://gisp.gov.ru/plp/p/api/', 'https://gisp.gov.ru/frp/p/api/',
          'https://gisp.gov.ru/support-measures/p/api/'):
    код, заг, тело = взять(u, 200, редиректы=False)
    редиректы[u] = {'код': код, 'location': заг.get('Location', ''),
                    'тип': заг.get('Content-Type', '')[:30]}
o['гисп_редиректы'] = редиректы

# 2. Страница региональных фондов на сайте ФРП — оттуда домены РФРП.
код, _, html = взять('https://frprf.ru/zaymy-regfondy/', 300000)
домены = sorted({m for m in re.findall(r'https?://([a-z0-9.\-]+\.(?:ru|рф))/', html)
                 if 'frprf.ru' not in m and 'gov.ru' not in m})
o['страница_регфондов'] = {'код': код, 'внешних_доменов': len(домены),
                           'домены': домены[:25]}

# 3. Карта региональных фондов: у ФРП есть страница со списком.
for u in ('https://frprf.ru/zaymy-regfondy/proekty-razvitiya-s-rfrp/',
          'https://frprf.ru/o-fonde/regionalnye-fondy/',
          'https://frprf.ru/regionalnye-fondy/'):
    код, _, h = взять(u, 300000)
    д = sorted({m for m in re.findall(r'https?://([a-z0-9.\-]+\.(?:ru|рф))/', h)
                if 'frprf.ru' not in m and 'gov.ru' not in m})
    o.setdefault('поиск_списка_фондов', {})[u] = {'код': код, 'доменов': len(д),
                                                  'примеры': д[:12]}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
