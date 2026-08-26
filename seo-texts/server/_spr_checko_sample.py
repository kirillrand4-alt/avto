# -*- coding: utf-8 -*-
"""Замер: какая доля наших БЕЗСАЙТОВЫХ компаний имеет сайт на checko /contacts.
Выборка стратифицирована: 80 по верхней выручке, 80 случайно из «с выручкой»,
40 случайно из «без выручки». Пишем в jsonl с fsync (durable)."""
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
OUT = r'C:\sender\_tmp\checko_sample.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')


def get(url, tmo=30):
    hd = {'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
          'Accept': 'text/html,application/xhtml+xml,*/*'}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=tmo) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception:
        return -1, ''


def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&quot;', '"'), ('&mdash;', '—'), ('&amp;', '&'),
                 ('&#8209;', '-'), ('&ndash;', '-')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


def разбор(t):
    d = {}
    m = re.search(r'Веб-сайт[ыа]?\s+(.{0,160}?)\s*(?:C?оциальные сети|Нашли ошибку|$)', t)
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
топ = cx.execute(Q + "AND COALESCE(revenue_rub,'') NOT IN ('','0') ORDER BY r DESC LIMIT 80").fetchall()
свыр = cx.execute(Q + "AND COALESCE(revenue_rub,'') NOT IN ('','0') ORDER BY random() LIMIT 80").fetchall()
безвыр = cx.execute(Q + "AND COALESCE(revenue_rub,'') IN ('','0') ORDER BY random() LIMIT 40").fetchall()
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
итог = {}
n, беды = 0, 0
t0 = time.time()
for слой, inn, ogrn, nm, reg, rev in цели:
    if inn in done or time.time() - t0 > 380:
        continue
    time.sleep(1.35)
    st, h = get('https://checko.ru/company/%s/contacts' % ogrn)
    if st in (429, 403, 503):
        беды += 1
        time.sleep(15 * беды)
        if беды >= 4:
            print('checko закрывается, отступаю', flush=True)
            break
        continue
    беды = 0
    t = plain(h)
    rec = {'слой': слой, 'inn': inn, 'ogrn': ogrn, 'name': nm, 'region': reg,
           'rev': rev, 'st': st, 'len': len(h)}
    rec.update(разбор(t))
    rec['инн_совпал'] = inn in t
    n += 1
    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    if n % 20 == 0:
        f.flush()
        os.fsync(f.fileno())
f.flush()
os.fsync(f.fileno())
f.close()
# сводка по всему файлу
ст = {}
for ln in io.open(OUT, encoding='utf-8', errors='replace'):
    try:
        r = json.loads(ln)
    except Exception:
        continue
    s = ст.setdefault(r['слой'], {'n': 0, 'ok200': 0, 'сайт': 0, 'почта': 0, 'тел': 0,
                                  'инн_на_стр': 0})
    s['n'] += 1
    s['ok200'] += r.get('st') == 200
    s['сайт'] += bool(r.get('sites'))
    s['почта'] += bool(r.get('emails'))
    s['тел'] += bool(r.get('phones'))
    s['инн_на_стр'] += bool(r.get('инн_совпал'))
print(json.dumps({'снято_сейчас': n, 'сводка': ст}, ensure_ascii=False))
