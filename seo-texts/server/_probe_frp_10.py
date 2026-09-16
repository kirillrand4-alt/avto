# -*- coding: utf-8 -*-
"""Проба 10: раздел clientage (истории успеха?), RSS ленты ФРП, разбор одной карточки новости."""
import re
import ssl
import sys
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))


def get(url, timeout=25):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    try:
        r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.status, dict(r.headers), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, dict(e.headers), e.read().decode('utf-8', 'replace')
        except Exception:                                    # noqa: BLE001
            return e.code, dict(e.headers), ''
    except Exception as e:                                   # noqa: BLE001
        return -1, {'err': str(e)[:140]}, ''


def plain(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).strip()


rep = []

# 1) clientage
for u in ('https://frprf.ru/clientage/', 'https://frprf.ru/sitemap-iblock-30.xml',
          'https://frprf.ru/sitemap-iblock-22.xml', 'https://frprf.ru/sitemap-iblock-28.xml',
          'https://frprf.ru/sitemap-iblock-37.xml', 'https://frprf.ru/sitemap-iblock-19.xml'):
    c, hd, h = get(u)
    if u.endswith('.xml'):
        locs = re.findall(r'<loc>([^<]+)</loc>', h)
        rep.append(f'{u} -> {c}, {len(locs)}: ' + ' | '.join(x[22:90] for x in locs[:10]))
    else:
        rep.append(f'{u} -> {c}, {len(h)} симв.; ' + plain(h)[:200])

# 2) RSS
rep.append('=== RSS')
for u in ('https://frprf.ru/rss/', 'https://frprf.ru/press-tsentr/novosti/rss/',
          'https://frprf.ru/press-tsentr/rss/', 'https://frprf.ru/news/rss/',
          'https://frprf.ru/press-tsentr/novosti/?rss=y', 'https://frprf.ru/rss.xml'):
    c, hd, h = get(u)
    rep.append(f'  {c} {len(h):>7} {(hd.get("Content-Type") or hd.get("err") or "")[:30]:<30} {u}'
               + ('  <rss!>' if '<rss' in h[:400] or '<feed' in h[:400] else ''))

# 3) карточка новости про заём
u = ('https://frprf.ru/press-tsentr/novosti/'
     'v-permi-blagodarya-zaymu-frp-otkryli-tsekh-po-proizvodstvu-neftyanykh-nasosnykh-agregatov-/')
c, hd, h = get(u)
rep.append(f'=== КАРТОЧКА {c} {len(h)} симв.')
# дата, теги, og-мета
for pat in (r'<meta[^>]+property="og:[^"]+"[^>]*>', r'class="date"[^>]*>([^<]{4,40})<',
            r'<h1[^>]*>(.*?)</h1>'):
    for m in re.findall(pat, h, re.S)[:6]:
        rep.append('   ' + re.sub(r'\s+', ' ', m if isinstance(m, str) else str(m))[:180])
body = plain(h)
i = body.find('Пермь') if 'Пермь' in body else 0
rep.append('   ТЕКСТ: ' + body[max(0, i - 200):i + 2400])

print('\n'.join(rep[-120:]))
sys.stdout.flush()
