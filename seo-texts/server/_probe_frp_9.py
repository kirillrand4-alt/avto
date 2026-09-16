# -*- coding: utf-8 -*-
"""Проба 9: где ещё лежат займы ФРП структурно.
Кандидаты: en.frprf.ru, реестр получателей поддержки ФНС (rmsp-pp), ГИСП, СПИК."""
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


def get(url, timeout=25, headers=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    try:
        r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, dict(e.headers), e.read()
        except Exception:                                    # noqa: BLE001
            return e.code, dict(e.headers), b''
    except Exception as e:                                   # noqa: BLE001
        return -1, {'err': str(e)[:140]}, b''


def line(u, timeout=25, headers=None):
    c, hd, b = get(u, timeout=timeout, headers=headers)
    s = b.decode('utf-8', 'replace')
    ttl = re.search(r'<title[^>]*>(.*?)</title>', s, re.S)
    ct = (hd.get('Content-Type') or hd.get('err') or '')[:40]
    return (f'  {c} {len(b):>8}b {ct:<34} {u}\n     title/начало: '
            + (re.sub(r'\s+', ' ', ttl.group(1)).strip()[:70] if ttl
               else re.sub(r'\s+', ' ', s)[:110]))


rep = []
rep.append('=== англоверсия ФРП')
for u in ('https://en.frprf.ru/', 'https://en.frprf.ru/clients/', 'https://en.frprf.ru/projects/'):
    rep.append(line(u))

rep.append('=== реестр получателей поддержки (ФНС)')
for u in ('https://rmsp-pp.nalog.ru/',
          'https://rmsp-pp.nalog.ru/index.html',
          'https://rmsp-pp.nalog.ru/open-data.html',
          'https://rmsp-pp.nalog.ru/statistics.html'):
    rep.append(line(u))

rep.append('=== ГИСП')
for u in ('https://gisp.gov.ru/', 'https://gisp.gov.ru/spik/', 'https://gisp.gov.ru/support-measures/',
          'https://gisp.gov.ru/nmp/measure/12448494'):
    rep.append(line(u))

rep.append('=== прочие реестры')
for u in ('https://minpromtorg.gov.ru/', 'https://frprf.ru/press-tsentr/novosti/?set_filter=y'
          '&arrFilter1_DATE_ACTIVE_FROM_1=01.08.2026&arrFilter1_DATE_ACTIVE_FROM_2=16.09.2026'):
    rep.append(line(u))

# у последнего — сколько карточек отдал фильтр по дате
c, hd, b = get('https://frprf.ru/press-tsentr/novosti/?set_filter=y'
               '&arrFilter1_DATE_ACTIVE_FROM_1=01.08.2026&arrFilter1_DATE_ACTIVE_FROM_2=16.09.2026')
s = b.decode('utf-8', 'replace')
links = sorted(set(re.findall(r'href="(/press-tsentr/novosti/[a-z0-9\-]{6,}/)"', s)))
pg = sorted({int(x) for x in re.findall(r'PAGEN_1=(\d+)', s)})
rep.append(f'ФИЛЬТР ПО ДАТЕ: {c}, карточек {len(links)}, PAGEN {pg[:10]}')

print('\n'.join(rep[-120:]))
sys.stdout.flush()
