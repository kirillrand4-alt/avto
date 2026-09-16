# -*- coding: utf-8 -*-
"""Проба 19: можно ли в реестре получателей поддержки ФНС фильтровать по организации,
предоставившей поддержку (ФРП), и что лежит в опендате. Только чтение."""
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))


def get(url, timeout=30, method=None):
    try:
        r = _OP.open(urllib.request.Request(
            url, headers={'User-Agent': UA, 'Accept': '*/*'}, method=method), timeout=timeout)
        return r.status, dict(r.headers), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, dict(e.headers), e.read().decode('utf-8', 'replace')
        except Exception:                                    # noqa: BLE001
            return e.code, dict(e.headers), ''
    except Exception as e:                                   # noqa: BLE001
        return -1, {}, str(e)[:120]


rep = []
B = 'https://rmsp-pp.nalog.ru/search-proc.json?'

# 1) кандидаты параметров фильтра по «поставщику поддержки»
for params in ({'query': ''},
               {'provider_inn': '7710964913'},
               {'providerInn': '7710964913'},
               {'query': '7710964913'},
               {'provider_organization': 'Фонд развития промышленности'},
               {'support_kind_code': '0101'},
               {'page': '2'}):
    c, h, s = get(B + urllib.parse.urlencode(params))
    try:
        d = json.loads(s)
        rows = d.get('data') or []
        prov = sorted({r.get('provider_inn') for r in rows})[:4]
        rep.append(f'  {params} -> {c}, rowCount={d.get("rowCount")}, строк {len(rows)}, '
                   f'provider_inn в выдаче: {prov}')
    except Exception:                                        # noqa: BLE001
        rep.append(f'  {params} -> {c}, не JSON: {s[:120]}')

# 2) какие вообще provider_organization попадаются на первой странице
c, h, s = get(B + 'page=1')
try:
    d = json.loads(s)
    orgs = {}
    for r in d.get('data') or []:
        orgs[(r.get('provider_inn'), str(r.get('provider_organization'))[:60])] = \
            orgs.get((r.get('provider_inn'), str(r.get('provider_organization'))[:60]), 0) + 1
    rep.append('  поставщики на стр.1: ' + json.dumps(
        [{'inn': k[0], 'org': k[1], 'n': v} for k, v in list(orgs.items())[:6]],
        ensure_ascii=False)[:600])
except Exception as e:                                       # noqa: BLE001
    rep.append('  ' + str(e)[:100])

# 3) опендата: файлы реестра
c, h, s = get('https://www.nalog.gov.ru/opendata/7707329152-rsmppp/')
rep.append(f'--- опендата rsmppp -> {c}, {len(s)} симв.')
for href in sorted({x for x in re.findall(r'href="([^"]+)"', s)
                    if re.search(r'\.(zip|csv|xml|json)(\?|$)', x, re.I)})[:12]:
    u = href if href.startswith('http') else 'https://www.nalog.gov.ru' + href
    c2, h2, _ = get(u, method='HEAD')
    rep.append(f'   файл {u[:110]} -> {c2}, {h2.get("Content-Length", "?")} байт, '
               f'{(h2.get("Content-Type") or "")[:30]}')
# описание набора (периодичность)
txt = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s)
txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', txt))
for kw in ('Периодичность', 'обновлени', 'Дата последнего'):
    for m in list(re.finditer(kw, txt, re.I))[:2]:
        rep.append('   ' + txt[max(0, m.start() - 60):m.start() + 160])

print('\n'.join(rep[-80:]))
sys.stdout.flush()
