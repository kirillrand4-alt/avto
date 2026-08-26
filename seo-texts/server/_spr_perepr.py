# -*- coding: utf-8 -*-
"""Перепроверка СВОЕГО счёта: те же ИНН, что через прокси дали «нет сайта»,
запрашиваем НАПРЯМУЮ. Если сайт появляется — виноват прокси, а не checko."""
import io
import json
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')


def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&quot;', '"'), ('&mdash;', '—'), ('&amp;', '&'),
                 ('&#8209;', '-'), ('&ndash;', '-')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


def сайты(t):
    m = re.search(r'Веб-сайт[ыа]?\s+(.{0,160}?)\s*(?:C?оциальные сети|Нашли ошибку)', t)
    if not m:
        return None
    return re.findall(r'\b[a-z0-9][a-z0-9\-]*\.[a-z]{2,10}(?:\.[a-z]{2,6})?\b',
                      m.group(1).lower())[:4]


def get(url, tmo=30):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'}), timeout=tmo) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception as e:
        return -1, str(e)[:50]


recs = [json.loads(l) for l in io.open(r'C:\sender\_tmp\checko_sample.jsonl',
                                       encoding='utf-8', errors='replace') if l.strip()]
цели = [r for r in recs if r['слой'] == 'топ' and r.get('via') == 'proxy'
        and not r.get('sites')][:18]
out = []
for r in цели:
    time.sleep(1.6)
    st, h = get('https://checko.ru/company/%s/contacts' % r['ogrn'])
    if st != 200:
        out.append([r['name'][:24], st, 'ОТКАЗ'])
        continue
    t = plain(h)
    out.append([r['name'][:24], int(r['rev'] / 1e6), сайты(t), len(h)])
print(json.dumps({'перепроверка_напрямую': out}, ensure_ascii=False)[:5500])
