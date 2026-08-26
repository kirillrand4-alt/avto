# -*- coding: utf-8 -*-
"""checko по ЧЕСТНЫМ полосам выручки. Сначала смотрим, как хранится revenue_rub,
потом 4 полосы по 90 компаний через прокси."""
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
OUT = r'C:\sender\_tmp\checko_polosy.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')
БЮДЖЕТ = 620.0
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

cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
СЫРЬЁ = cx.execute("SELECT revenue_rub FROM companies WHERE COALESCE(revenue_rub,'')!='' "
                   "LIMIT 6").fetchall()
БАЗА = ("FROM companies WHERE COALESCE(site,'')='' AND COALESCE(cand_site,'')='' "
        "AND COALESCE(ogrn,'')!='' ")
ПОЛОСЫ = {
    'A_1млрд+': "AND CAST(revenue_rub AS REAL)>=1e9",
    'B_100м-1млрд': "AND CAST(revenue_rub AS REAL)>=1e8 AND CAST(revenue_rub AS REAL)<1e9",
    'C_10-100м': "AND CAST(revenue_rub AS REAL)>=1e7 AND CAST(revenue_rub AS REAL)<1e8",
    'D_меньше10м': "AND CAST(COALESCE(revenue_rub,0) AS REAL)<1e7",
}
РАЗМЕР = {}
цели = []
for имя, усл in ПОЛОСЫ.items():
    РАЗМЕР[имя] = cx.execute("SELECT COUNT(*) " + БАЗА + усл).fetchone()[0]
    for r in cx.execute("SELECT inn, ogrn, substr(name,1,44), region, "
                        "CAST(COALESCE(revenue_rub,0) AS REAL) " + БАЗА + усл
                        + " ORDER BY random() LIMIT 90"):
        цели.append((имя, *r))
cx.close()

def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&quot;', '"'), ('&mdash;', '—'), ('&amp;', '&'),
                 ('&#8209;', '-'), ('&ndash;', '-')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


def разбор(t):
    o = {}
    m = re.search(r'Веб-сайт[ыа]?\s+(.{0,160}?)\s*(?:C?оциальные сети|Нашли ошибку)', t)
    if m:
        o['sites'] = re.findall(r'\b[a-z0-9][a-z0-9\-]*\.[a-z]{2,10}(?:\.[a-z]{2,6})?\b',
                                m.group(1).lower())[:4]
    m = re.search(r'Электронная почта\s+(.{0,220}?)\s*(?:Веб-сайт|C?оциальные|Нашли)', t)
    if m:
        o['emails'] = re.findall(r'[\w.\-+]+@[\w.\-]+\.[a-z]{2,8}', m.group(1))[:5]
    m = re.search(r'Телефоны?\s+(.{0,200}?)\s*(?:Электронная|Веб-сайт|C?оциальные|Нашли)', t)
    if m:
        o['phones'] = re.findall(r'\+7[\d\s\-()]{9,18}', m.group(1))[:5]
    return o


done = set()
if os.path.exists(OUT):
    for ln in io.open(OUT, encoding='utf-8', errors='replace'):
        try:
            done.add(json.loads(ln)['inn'])
        except Exception:
            pass
f = io.open(OUT, 'a', encoding='utf-8')
n, k, отказ = 0, 0, 0
for пол, inn, ogrn, nm, reg, rev in цели:
    if inn in done or time.time() - t0 > БЮДЖЕТ:
        continue
    px = PX[k % len(PX)] if PX else None
    k += 1
    time.sleep(0.72)
    try:
        r = requests.get('https://checko.ru/company/%s/contacts' % ogrn,
                         headers={'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'},
                         proxies={'http': px, 'https': px} if px else None, timeout=28)
        st, h = r.status_code, r.text
    except Exception:
        st, h = -1, ''
    if st != 200:
        отказ += 1
        continue
    t = plain(h)
    rec = {'полоса': пол, 'inn': inn, 'ogrn': ogrn, 'name': nm, 'region': reg,
           'rev': rev, 'len': len(h)}
    rec.update(разбор(t))
    n += 1
    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    if n % 25 == 0:
        f.flush()
        os.fsync(f.fileno())
f.flush()
os.fsync(f.fileno())
f.close()
св = {}
for ln in io.open(OUT, encoding='utf-8', errors='replace'):
    try:
        r = json.loads(ln)
    except Exception:
        continue
    s = св.setdefault(r['полоса'], {'n': 0, 'сайт': 0, 'почта': 0, 'тел': 0})
    s['n'] += 1
    s['сайт'] += bool(r.get('sites'))
    s['почта'] += bool(r.get('emails'))
    s['тел'] += bool(r.get('phones'))
print(json.dumps({'сырьё_revenue': СЫРЬЁ, 'размер_полос_в_базе': РАЗМЕР,
                  'снято': n, 'отказов': отказ, 'сводка': св}, ensure_ascii=False)[:5600])
