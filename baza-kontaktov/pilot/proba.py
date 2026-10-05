# -*- coding: utf-8 -*-
"""Проба XMLRiver: варианты гео/глубины, docs и списание по каждому (баланс до/после)."""
import os, re, time, json, urllib.parse, urllib.request
U, K = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
A = urllib.parse.urlencode({'user': U, 'key': K})
_D = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def bal():
    return float(_D.open('http://xmlriver.com/api/get_balance/?' + A, timeout=30).read())


def call(eng, q, extra):
    base = 'search_yandex/xml?' + A + '&domain=ru&device=desktop' if eng == 'y' else 'search/xml?' + A + '&device=desktop'
    x = _D.open('http://xmlriver.com/' + base + extra + '&query=' + urllib.parse.quote(q), timeout=90).read().decode('utf-8', 'replace')
    urls = re.findall(r'<url>(.*?)</url>', x)
    er = re.search(r'<error[^>]*>(.*?)</error>', x, re.S)
    return len(re.findall(r'<doc>', x)), (er.group(1)[:80] if er else ''), [re.sub(r'https?://(www\.)?', '', u)[:40] for u in urls[:4]]


V = [
    ('y', 'элеватор Алтайский край', '&lr=11235&groupby=10&page=0'),
    ('y', 'элеватор Алтайский край', '&lr=11235&groupby=50&page=0'),
    ('y', 'элеватор Алтайский край', '&lr=11235&groupby=10&page=1'),
    ('y', 'голубика плантация Брестская область', '&domain=by&lr=29632&groupby=10'),
    ('y', 'семена пшеницы производитель Краснодарский край', '&lr=10995&groupby=10'),
    ('g', 'элеватор Алтайский край', '&country=2643&page=1'),
    ('g', 'элеватор Алтайский край', '&country=2643&page=2'),
    ('g', 'элеватор Алтайский край', '&page=1'),
    ('g', 'голубика плантация Брестская область', '&country=2112&page=1'),
    ('g', 'экспортёр нута', '&country=2643&page=1'),
]
out = []
b0 = bal()
for e, q, ex in V:
    b1 = bal()
    try:
        n, er, us = call(e, q, ex)
    except Exception as x:  # noqa: BLE001
        n, er, us = 0, type(x).__name__ + str(x)[:60], []
    time.sleep(1)
    b2 = bal()
    out.append({'e': e, 'q': q[:40], 'ex': ex, 'docs': n, 'err': er, 'spent': round(b1 - b2, 4), 'urls': us})
print('===ИТОГ===')
for o in out:
    print(json.dumps(o, ensure_ascii=False))
print('баланс', b0, '->', bal())
