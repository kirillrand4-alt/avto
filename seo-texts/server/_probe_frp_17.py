# -*- coding: utf-8 -*-
"""Проба 17 (доп. раздел ТЗ): есть ли публичные реестры у СПИК / СЗПК / субсидий
Минпромторга. Только чтение + печать кодов/заголовков."""
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


def probe(url, timeout=20, accept='text/html,*/*'):
    try:
        r = _OP.open(urllib.request.Request(
            url, headers={'User-Agent': UA, 'Accept': accept}), timeout=timeout)
        b = r.read()
        s = b.decode('utf-8', 'replace')
        code, ct = r.status, (r.headers.get('Content-Type') or '')[:35]
    except urllib.error.HTTPError as e:
        try:
            s = e.read().decode('utf-8', 'replace')
        except Exception:                                    # noqa: BLE001
            s = ''
        code, ct, b = e.code, (e.headers.get('Content-Type') or '')[:35], b''
    except Exception as e:                                   # noqa: BLE001
        return f'  -1 {str(e)[:60]:<60} {url}'
    t = re.search(r'<title[^>]*>(.*?)</title>', s, re.S)
    head = (re.sub(r'\s+', ' ', t.group(1)).strip()[:60] if t
            else re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))[:70])
    js = 'JSON' if s[:200].lstrip().startswith(('{', '[')) else ''
    return f'  {code} {len(s):>8} {ct:<35} {js:<5} {url}\n       {head}'


URLS = [
    ('СПИК (ГИСП)', ['https://gisp.gov.ru/spik/',
                     'https://gisp.gov.ru/spik-registry/',
                     'https://gisp.gov.ru/opendata/',
                     'https://gisp.gov.ru/documents/']),
    ('СПИК (Минпромторг)', ['https://minpromtorg.gov.ru/activities/gosudarstvennaya-podderzhka/spik/',
                            'https://minpromtorg.gov.ru/opendata/']),
    ('СЗПК', ['https://www.economy.gov.ru/material/directions/investicionnaya_deyatelnost/'
              'mehanizm_szpk/', 'https://gisk.veb.ru/', 'https://xn--80aapampemcchfmo7a3c9ehj.xn--p1ai/',
              'https://investmoscow.ru/']),
    ('Субсидии (Электронный бюджет)', ['https://promote.budget.gov.ru/',
                                       'https://budget.gov.ru/',
                                       'https://promote.budget.gov.ru/public/nsi/']),
    ('Прочее', ['https://www.nalog.gov.ru/opendata/7707329152-rsmppp/',
                'https://rmsp-pp.nalog.ru/search-proc.json',
                'https://xn--l1agf.xn--p1ai/']),
]
rep = []
for name, urls in URLS:
    rep.append('=== ' + name)
    for u in urls:
        rep.append(probe(u))
print('\n'.join(rep[-120:]))
sys.stdout.flush()
