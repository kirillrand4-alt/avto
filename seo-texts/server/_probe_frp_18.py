# -*- coding: utf-8 -*-
"""Проба 18: JSON-ручка реестра получателей поддержки ФНС + открытые данные Минпромторга.
Только чтение."""
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


def get(url, timeout=25, data=None):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if data:
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        r = _OP.open(urllib.request.Request(url, headers=h, data=data), timeout=timeout)
        return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace')
        except Exception:                                    # noqa: BLE001
            return e.code, ''
    except Exception as e:                                   # noqa: BLE001
        return -1, str(e)[:120]


rep = []

# 1) ручка без параметров
c, s = get('https://rmsp-pp.nalog.ru/search-proc.json')
rep.append(f'search-proc.json (без параметров) -> {c}, {len(s)} симв.')
try:
    d = json.loads(s)
    rep.append('  ключи ответа: ' + str(list(d)[:20]))
    rows = d.get('rows') or d.get('data') or []
    rep.append(f'  строк: {len(rows)}; pageCount={d.get("pageCount")}')
    if rows:
        rep.append('  поля строки: ' + str(list(rows[0])[:25]))
        rep.append('  пример строки: ' + json.dumps(rows[0], ensure_ascii=False)[:700])
except Exception as e:                                       # noqa: BLE001
    rep.append('  не JSON: ' + str(e)[:80] + ' | ' + s[:300])

# 2) поля формы расширенного поиска (какие параметры принимает ручка)
c, s = get('https://rmsp-pp.nalog.ru/index.html')
names = sorted(set(re.findall(r'<(?:input|select)[^>]*name="([^"]+)"', s)))
rep.append('поля формы: ' + str(names[:40]))
ids = sorted(set(re.findall(r'id="(query|org|support|kind|form|period|region)[^"]*"', s)))
rep.append('  id-шники: ' + str(ids[:30]))
# что шлёт JS
for m in re.findall(r'search-proc\.json[^"\']{0,200}', s)[:5]:
    rep.append('  в html: ' + m[:200])
c2, js = get('https://rmsp-pp.nalog.ru/static/js/main.js')
if c2 == 200:
    for m in re.findall(r'search-proc[^\n]{0,300}', js)[:5]:
        rep.append('  main.js: ' + m[:300])

# 3) попробовать поиск по организации, предоставившей поддержку
for q in ('Фонд развития промышленности', 'ФРП'):
    u = 'https://rmsp-pp.nalog.ru/search-proc.json?' + urllib.parse.urlencode(
        {'mode': 'quick', 'query': q, 'page': 1})
    c3, s3 = get(u)
    rep.append(f'поиск «{q}» -> {c3}, {len(s3)} симв.; начало: ' + s3[:300].replace('\n', ' '))

# 4) открытые данные Минпромторга — какие наборы есть
c4, s4 = get('https://minpromtorg.gov.ru/opendata/')
rep.append(f'--- minpromtorg/opendata -> {c4}, {len(s4)}')
seen = set()
for href, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.{0,200}?)</a>', s4, re.S):
    tt = re.sub(r'<[^>]+>|\s+', ' ', t).strip()
    if re.search(r'субсид|СПИК|за[ёе]м|поддержк|инвест|реестр', tt, re.I) and tt not in seen:
        seen.add(tt)
        rep.append(f'   набор: «{tt[:90]}» -> {href[:90]}')

print('\n'.join(rep[-120:]))
sys.stdout.flush()
