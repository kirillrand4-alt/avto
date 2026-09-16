# -*- coding: utf-8 -*-
"""Проба 13: отладка парсера карточек ленты ФРП — что реально в HTML."""
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
    try:
        r = _OP.open(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=timeout)
        return r.status, r.read().decode('utf-8', 'replace')
    except Exception as e:                                   # noqa: BLE001
        return -1, str(e)[:120]


rep = []
for u in ('https://frprf.ru/press-tsentr/novosti/',
          'https://frprf.ru/press-tsentr/novosti/?PAGEN_1=100',
          'https://frprf.ru/press-tsentr/novosti/?set_filter=y'
          '&arrFilter1_DATE_ACTIVE_FROM_1=01.06.2026&arrFilter1_DATE_ACTIVE_FROM_2=16.09.2026'):
    c, h = get(u)
    rep.append(f'--- {c} {len(h)} {u[:100]}')
    rep.append('   item-news: %d | class="date": %d | class="title": %d | ссылок-новостей: %d'
               % (h.count('item-news'), h.count('class="date"'), h.count('class="title"'),
                  len(set(re.findall(r'href="(/press-tsentr/novosti/[a-z0-9\-]{6,}/)"', h)))))
    i = h.find('item-news')
    if i > 0:
        rep.append('   фрагмент: ' + re.sub(r'\s+', ' ', h[i - 30:i + 900]))
    # даты в ленте
    rep.append('   даты: ' + str(re.findall(r'class="date"[^>]*>\s*([^<]{4,30}?)\s*<', h)[:8]))

print('\n'.join(rep[-60:]))
sys.stdout.flush()
