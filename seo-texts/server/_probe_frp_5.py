# -*- coding: utf-8 -*-
"""Проба 5: карта проектов (vmap_fact.js), файлы сайта, поиск по сайту «реестр/профинансированные».
Только чтение сети + печать."""
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


def get(url, timeout=30, headers=None, data=None, method=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h, data=data, method=method)
        r = _OP.open(req, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:                                    # noqa: BLE001
            return e.code, b''
    except Exception as e:                                   # noqa: BLE001
        return -1, str(e)[:160].encode()


def plain(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


rep = []

# 1) карта
for u in ('https://frprf.ru/asset/vmap/vmap_fact.js',
          'https://frprf.ru/asset/vmap/app.map.partners.add.js',
          'https://frprf.ru/asset/vmap/script.js'):
    c, b = get(u)
    s = b.decode('utf-8', 'replace')
    rep.append(f'--- {u} -> {c} {len(s)} симв.')
    rep.append('   URLы внутри: ' + str(sorted(set(re.findall(r'["\'](/[^"\']{3,90})["\']', s)))[:15]))
    rep.append('   начало: ' + re.sub(r'\s+', ' ', s)[:600])

# 2) файлы сайта
c, b = get('https://frprf.ru/sitemap-files.xml')
for u in re.findall(r'<loc>([^<]+)</loc>', b.decode('utf-8', 'replace')):
    rep.append('   ФАЙЛ: ' + u)

# 3) поиск по сайту
for q in ('профинансированные проекты', 'реестр проектов', 'карта проектов'):
    u = 'https://frprf.ru/search/?q=' + urllib.parse.quote(q)
    c, b = get(u)
    h = b.decode('utf-8', 'replace')
    rep.append(f'--- ПОИСК «{q}» -> {c} {len(h)}')
    body = plain(h)
    m = re.search(r'(Результаты поиска|Найдено|Ничего не найдено)[^|]{0,200}', body)
    rep.append('   ' + (m.group(0)[:200] if m else body[:200]))
    for href, t in re.findall(r'<a[^>]+href="(/[^"#]{4,90})"[^>]*>(.{0,120}?)</a>', h, re.S):
        tt = re.sub(r'<[^>]+>|\s+', ' ', t).strip()
        if re.search(r'проект|реестр|карт', tt, re.I) and not href.startswith('/zaymy'):
            rep.append(f'   найдено: «{tt[:70]}» -> {href}')

# 4) кандидаты разделов
for u in ('https://frprf.ru/o-fonde/rezultaty/', 'https://frprf.ru/o-fonde/statistika/',
          'https://frprf.ru/klienty/42484/', 'https://frprf.ru/proekty-fonda/',
          'https://frprf.ru/o-fonde/proekty/'):
    c, b = get(u)
    h = b.decode('utf-8', 'replace')
    ttl = re.search(r'<title[^>]*>(.*?)</title>', h, re.S)
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
    rep.append(f'  {c} {len(h):>7} {u} | title='
               + (re.sub(r'\s+', ' ', ttl.group(1)).strip()[:50] if ttl else '')
               + ' | h1=' + (re.sub(r'<[^>]+>|\s+', ' ', h1.group(1)).strip()[:60] if h1 else ''))

print('\n'.join(rep[-140:]))
sys.stdout.flush()
