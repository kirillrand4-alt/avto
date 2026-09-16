# -*- coding: utf-8 -*-
"""Проба 8: новостная лента ФРП — пагинация, структура карточки, фильтры; агрегаты по проектам."""
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


def get(url, timeout=30):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    try:
        r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace')
        except Exception:                                    # noqa: BLE001
            return e.code, ''
    except Exception as e:                                   # noqa: BLE001
        return -1, str(e)[:150]


def plain(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).strip()


rep = []

# 1) лента новостей: страница 1 и 5
for u in ('https://frprf.ru/press-tsentr/novosti/',
          'https://frprf.ru/press-tsentr/novosti/?PAGEN_1=5',
          'https://frprf.ru/press-tsentr/novosti/?PAGEN_1=200'):
    c, h = get(u)
    links = sorted(set(re.findall(r'href="(/press-tsentr/novosti/[a-z0-9\-]{6,}/)"', h)))
    pg = sorted({int(x) for x in re.findall(r'PAGEN_1=(\d+)', h)})
    rep.append(f'--- {u} -> {c} {len(h)} симв.; карточек {len(links)}; PAGEN max={pg[-1] if pg else "-"}')
    rep.append('   первые ссылки: ' + ' | '.join(x[:70] for x in links[:3]))

# 2) блок одной карточки в ленте (как выглядит HTML вокруг ссылки)
c, h = get('https://frprf.ru/press-tsentr/novosti/')
m = re.search(r'href="(/press-tsentr/novosti/[a-z0-9\-]{6,}/)"', h)
if m:
    s = max(0, m.start() - 1200)
    rep.append('--- HTML вокруг карточки: ' + re.sub(r'\s+', ' ', h[s:m.end() + 900])[:2200])

# 3) фильтры ленты (селекты/инпуты)
rep.append('--- select/input в ленте: ' + str(sorted(set(re.findall(r'<(?:select|input)[^>]*name="([^"]+)"', h)))[:20]))
rep.append('--- GET-параметры в ссылках ленты: '
           + str(sorted({x for x in re.findall(r'href="/press-tsentr/novosti/\?([^"]{2,60})"', h)})[:20]))

# 4) агрегаты по проектам (сколько всего профинансировано)
c2, h2 = get('https://frprf.ru/o-fonde/')
p2 = plain(h2)
for kw in ('профинансиров', 'проект', 'займ'):
    for m2 in list(re.finditer(kw, p2, re.I))[:4]:
        rep.append(f'   [{kw}] ...' + p2[max(0, m2.start() - 130):m2.start() + 170] + '...')

print('\n'.join(rep[-120:]))
sys.stdout.flush()
