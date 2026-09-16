# -*- coding: utf-8 -*-
"""Проба 15: сырой HTML карточки (repr, без схлопывания пробелов) — почему не ловятся регексы."""
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
r = _OP.open(urllib.request.Request('https://frprf.ru/press-tsentr/novosti/',
                                    headers={'User-Agent': UA}), timeout=25)
h = r.read().decode('utf-8', 'replace')
rep = [f'код {r.status}, длина {len(h)}']
parts = re.split(r'class="item-news', h)
rep.append(f'split по class="item-news": кусков {len(parts)}')
i = h.find('class="title"')
rep.append('repr вокруг class="title": ' + repr(h[i - 120:i + 420]))
blk = parts[1] if len(parts) > 1 else ''
rep.append('в куске: title=%s date=%s a=%s'
           % (bool(re.search(r'class="title">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)),
              bool(re.search(r'class="date"[^>]*>\s*([^<]+?)\s*<', blk)),
              bool(re.search(r'<a href="(/press-tsentr/novosti/[^"]+)"', blk))))
rep.append('repr начала куска: ' + repr(blk[:700]))
print('\n'.join(rep))
sys.stdout.flush()
