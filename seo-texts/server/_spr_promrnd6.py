# -*- coding: utf-8 -*-
"""promrnd: добрать оставшиеся id из каталожной страницы (они идут до 3923,
мой перебор дошёл только до 1025)."""
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
OUT = r'C:\sender\_tmp\promrnd_sites.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')
t0 = time.time()


def get(url, tmo=30):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'}), timeout=tmo) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception:
        return -1, ''


def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', h.replace('&nbsp;', ' ').replace('&quot;', '"'))


st, h = get('https://promrnd.ru/company/')
кат = sorted({int(x) for x in re.findall(r'/company/(\d+)/', h)})
done = set()
if os.path.exists(OUT):
    for ln in io.open(OUT, encoding='utf-8', errors='replace'):
        try:
            done.add(json.loads(ln)['id'])
        except Exception:
            pass
надо = [i for i in кат if i not in done]
print('добрать', len(надо), flush=True)
f = io.open(OUT, 'a', encoding='utf-8')
n = 0
for i in надо:
    if time.time() - t0 > 470:
        break
    time.sleep(1.15)
    st, h = get('https://promrnd.ru/company/%d/' % i)
    if st != 200:
        continue
    t = plain(h)
    m = re.search(r'href="(https?://[^"]+)"[^>]*>\s*Перейти на сайт компании', h)
    rec = {'id': i, 'inn': (re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t) or [''])[0],
           'name': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0][:90],
           'site': m.group(1) if m else '',
           'на_портале_с': (re.findall(r'На портале с\s*([\d.]{8,10})', t) or [''])[0]}
    n += 1
    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    if n % 25 == 0:
        f.flush()
        os.fsync(f.fileno())
f.flush()
os.fsync(f.fileno())
f.close()
recs = [json.loads(l) for l in io.open(OUT, encoding='utf-8', errors='replace') if l.strip()]
дом = {}
for x in recs:
    d = re.sub(r'^https?://', '', x['site'] or '').split('/')[0].lower()
    d = d[4:] if d.startswith('www.') else d
    if d:
        дом.setdefault(d, []).append(x['inn'])
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
инны = [x['inn'] for x in recs if x['inn']]
наши = {}
for i in range(0, len(инны), 400):
    part = инны[i:i + 400]
    for r in cx.execute("SELECT inn, name, COALESCE(revenue_rub,0), COALESCE(site,''), "
                        "COALESCE(cand_site,'') FROM companies WHERE inn IN (%s)"
                        % ','.join('?' * len(part)), part):
        наши[r[0]] = r
cx.close()
нах = [x for x in recs if наши.get(x['inn']) and not наши[x['inn']][3]
       and not наши[x['inn']][4] and x['site']]
print(json.dumps({
    'добрано_сейчас': n, 'id_в_каталоге': len(кат), 'проверено_всего': len(recs),
    'осталось': len([i for i in кат if i not in {x['id'] for x in recs}]),
    'с_ИНН': len(инны), 'с_сайтом': sum(1 for x in recs if x['site']),
    'уникальных_доменов': len(дом),
    'домен_на_2+': sorted(((len(v), k) for k, v in дом.items() if len(v) > 1), reverse=True)[:5],
    'наших': len(наши), 'НЕ_наших': len(set(инны)) - len(наши),
    'наших_без_сайта': sum(1 for r in наши.values() if not r[3] and not r[4]),
    'находок': len(нах)}, ensure_ascii=False)[:3000])
