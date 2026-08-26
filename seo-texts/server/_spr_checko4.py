# -*- coding: utf-8 -*-
"""Чиню свой же счёт: revenue_rub — ЧИСЛО, сравнение с '0' в SQLite ложное.
Пересчёт населения + проверка, что «Веб-сайт» на странице вообще есть (пусто ли
поле или его нет), на полосе с NULL-выручкой и на полосе 1млрд+."""
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
OUT = r'C:\sender\_tmp\checko_polosy2.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')
t0 = time.time()
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
БС = "COALESCE(site,'')='' AND COALESCE(cand_site,'')=''"
O = {'население': dict(zip(
    ['всего', 'без_сайта', 'без_сайта_и_ogrn_есть', 'выручка_NULL', 'выручка_0',
     'выр>=1e6', 'выр>=1e7', 'выр>=1e8', 'выр>=1e9',
     'бс_выр_NULL', 'бс_выр_0', 'бс_выр>=1e6', 'бс_выр>=1e7', 'бс_выр>=1e8'],
    cx.execute(f"""SELECT COUNT(*), SUM({БС}), SUM({БС} AND COALESCE(ogrn,'')!=''),
      SUM(revenue_rub IS NULL), SUM(revenue_rub=0),
      SUM(revenue_rub>=1e6), SUM(revenue_rub>=1e7), SUM(revenue_rub>=1e8),
      SUM(revenue_rub>=1e9),
      SUM({БС} AND revenue_rub IS NULL), SUM({БС} AND revenue_rub=0),
      SUM({БС} AND revenue_rub>=1e6), SUM({БС} AND revenue_rub>=1e7),
      SUM({БС} AND revenue_rub>=1e8) FROM companies""").fetchone()))}
цели = []
for имя, усл in (('NULL_выручка', 'AND revenue_rub IS NULL'),
                 ('E_1-10м', 'AND revenue_rub>=1e6 AND revenue_rub<1e7')):
    for r in cx.execute(f"SELECT inn, ogrn, substr(name,1,40), region, "
                        f"COALESCE(revenue_rub,0) FROM companies WHERE {БС} "
                        f"AND COALESCE(ogrn,'')!='' {усл} ORDER BY random() LIMIT 70"):
        цели.append((имя, *r))
cx.close()
d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
req = urllib.request.Request(
    os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
    + '/dolphin-proxies.txt', headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
PX = []
for l in d.open(req, timeout=30).read().decode('utf-8', 'replace').splitlines():
    l = l.strip()
    m = re.match(r'(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', l) if l and not l.startswith('#') else None
    if m:
        u, p, h, _ = m.groups()
        PX.append('socks5://%s:%s@%s:3001' % (u, p, h))


def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&quot;', '"'), ('&mdash;', '—'), ('&amp;', '&'),
                 ('&#8209;', '-'), ('&ndash;', '-')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


f = io.open(OUT, 'a', encoding='utf-8')
n, k = 0, 0
for пол, inn, ogrn, nm, reg, rev in цели:
    if time.time() - t0 > 380:
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
        continue
    if st != 200:
        continue
    t = plain(h)
    m = re.search(r'Веб-сайт[ыа]?\s+(.{0,160}?)\s*(?:C?оциальные сети|Нашли ошибку)', t)
    val = m.group(1).strip() if m else ''
    sites = re.findall(r'\b[a-z0-9][a-z0-9\-]*\.[a-z]{2,10}\b', val.lower())[:3]
    rec = {'полоса': пол, 'inn': inn, 'name': nm, 'rev': rev,
           'есть_строка': bool(m), 'значение': val[:60], 'sites': sites}
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
    s = св.setdefault(r['полоса'], {'n': 0, 'строка_есть': 0, 'сайт': 0, 'примеры': []})
    s['n'] += 1
    s['строка_есть'] += bool(r['есть_строка'])
    s['сайт'] += bool(r['sites'])
    if r['sites'] and len(s['примеры']) < 5:
        s['примеры'].append([r['name'][:24], r['sites'], int(r['rev'])])
O['проба'] = св
print(json.dumps(O, ensure_ascii=False)[:5600])
