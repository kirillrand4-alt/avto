# -*- coding: utf-8 -*-
"""Замер checko через пул прокси: ротация IP (лимит ~40 запросов на IP),
но суммарно не больше ~1,3 запроса в секунду на домен checko.ru.
Выборка: 100 топ по выручке + 100 случайных с выручкой + 100 без выручки."""
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
OUT = r'C:\sender\_tmp\checko_sample.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')
БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 400.0
t0 = time.time()

d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
req = urllib.request.Request(
    os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
    + '/dolphin-proxies.txt',
    headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
PX = []
for l in d.open(req, timeout=30).read().decode('utf-8', 'replace').splitlines():
    l = l.strip()
    m = re.match(r'(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', l) if l and not l.startswith('#') else None
    if m:
        u, p, h, _ = m.groups()
        PX.append('socks5://%s:%s@%s:3001' % (u, p, h))
print('прокси', len(PX), flush=True)


def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&quot;', '"'), ('&mdash;', '—'), ('&amp;', '&'),
                 ('&#8209;', '-'), ('&ndash;', '-')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


def разбор(t):
    d = {}
    m = re.search(r'Веб-сайт[ыа]?\s+(.{0,160}?)\s*(?:C?оциальные сети|Нашли ошибку)', t)
    if m:
        d['sites'] = re.findall(r'\b[a-z0-9][a-z0-9\-]*\.[a-z]{2,10}(?:\.[a-z]{2,6})?\b',
                                m.group(1).lower())[:4]
    m = re.search(r'Электронная почта\s+(.{0,220}?)\s*(?:Веб-сайт|C?оциальные|Нашли)', t)
    if m:
        d['emails'] = re.findall(r'[\w.\-+]+@[\w.\-]+\.[a-z]{2,8}', m.group(1))[:5]
    m = re.search(r'Телефоны?\s+(.{0,200}?)\s*(?:Электронная|Веб-сайт|C?оциальные|Нашли)', t)
    if m:
        d['phones'] = re.findall(r'\+7[\d\s\-()]{9,18}', m.group(1))[:5]
    return d


cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
Q = ("SELECT inn, ogrn, substr(name,1,50), region, CAST(COALESCE(revenue_rub,0) AS REAL) r "
     "FROM companies WHERE COALESCE(site,'')='' AND COALESCE(cand_site,'')='' "
     "AND COALESCE(ogrn,'')!='' ")
топ = cx.execute(Q + "AND COALESCE(revenue_rub,'') NOT IN ('','0') ORDER BY r DESC LIMIT 130").fetchall()
свыр = cx.execute(Q + "AND COALESCE(revenue_rub,'') NOT IN ('','0') ORDER BY random() LIMIT 120").fetchall()
безвыр = cx.execute(Q + "AND COALESCE(revenue_rub,'') IN ('','0') ORDER BY random() LIMIT 120").fetchall()
cx.close()
цели = ([('топ', *x) for x in топ] + [('с_выручкой', *x) for x in свыр]
        + [('без_выручки', *x) for x in безвыр])
done = set()
if os.path.exists(OUT):
    for ln in io.open(OUT, encoding='utf-8', errors='replace'):
        try:
            done.add(json.loads(ln)['inn'])
        except Exception:
            pass
f = io.open(OUT, 'a', encoding='utf-8')
n, k, беды = 0, 0, 0
for слой, inn, ogrn, nm, reg, rev in цели:
    if inn in done or time.time() - t0 > БЮДЖЕТ:
        continue
    px = PX[k % len(PX)] if PX else None
    k += 1
    time.sleep(0.75)
    st, h = 0, ''
    try:
        r = requests.get('https://checko.ru/company/%s/contacts' % ogrn,
                         headers={'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'},
                         proxies={'http': px, 'https': px} if px else None, timeout=30)
        st, h = r.status_code, r.text
    except Exception as e:
        st, h = -1, str(e)[:60]
    if st in (429, 403, 503):
        беды += 1
        if беды >= 12:
            print('checko: слишком много отказов, стоп', flush=True)
            break
        continue
    if st != 200:
        continue
    беды = 0
    t = plain(h)
    rec = {'слой': слой, 'inn': inn, 'ogrn': ogrn, 'name': nm, 'region': reg,
           'rev': rev, 'st': st, 'len': len(h), 'via': 'proxy'}
    rec.update(разбор(t))
    rec['инн_совпал'] = inn in t
    n += 1
    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    if n % 20 == 0:
        f.flush()
        os.fsync(f.fileno())
        print('checko', n, flush=True)
f.flush()
os.fsync(f.fileno())
f.close()
ст = {}
for ln in io.open(OUT, encoding='utf-8', errors='replace'):
    try:
        r = json.loads(ln)
    except Exception:
        continue
    s = ст.setdefault(r['слой'], {'n': 0, 'сайт': 0, 'почта': 0, 'тел': 0})
    s['n'] += 1
    s['сайт'] += bool(r.get('sites'))
    s['почта'] += bool(r.get('emails'))
    s['тел'] += bool(r.get('phones'))
print(json.dumps({'снято': n, 'отказов': беды, 'сводка': ст}, ensure_ascii=False))
