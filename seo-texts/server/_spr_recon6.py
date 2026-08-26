# -*- coding: utf-8 -*-
"""Разведка 6: кто писал site_checko; строение карточек agrobase (apk/dealers);
   поведение checko при подряд идущих запросах (без прокси, прямо с сервера)."""
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
O = {}
# 1. кто пишет site_checko
hits = []
for base in (r'C:\sender\server', r'C:\sender\_ops', r'C:\sender\ops'):
    if not os.path.isdir(base):
        continue
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d.lower() not in ('node_modules', '.git', '__pycache__')]
        for fn in files:
            if not fn.endswith('.py') or '.bak' in fn:
                continue
            fp = os.path.join(root, fn)
            try:
                s = open(fp, encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            if 'site_checko' in s:
                frags = [re.sub(r'\s+', ' ', s[max(0, m.start() - 260):m.start() + 200])
                         for m in list(re.finditer(r'site_checko', s))[:2]]
                hits.append({'файл': fp, 'фрагменты': frags})
O['пишут_site_checko'] = hits[:6]

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')


def get(url, tmo=40):
    hd = {'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
          'Accept': 'text/html,application/xhtml+xml,*/*'}
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=tmo) as r:
            raw = r.read()
            enc = 'utf-8'
            m = re.search(r'charset=([\w-]+)', r.headers.get('Content-Type', ''))
            if m:
                enc = m.group(1)
            return r.status, raw.decode(enc, 'replace'), time.time() - t0
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace'), time.time() - t0
        except Exception:
            return e.code, '', time.time() - t0
    except Exception as e:
        return -1, str(e)[:100], time.time() - t0


def plain(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(
        r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)))


P = {}
# 2. agrobase: пример apk и dealer из сохранённых карт сайта? качаем свежие
for nm in ('sitemap_apk.xml', 'sitemap_dealers.xml'):
    st, h, _ = get('https://www.agrobase.ru/' + nm)
    urls = re.findall(r'<loc>([^<]+)</loc>', h)
    P[nm] = {'n': len(urls), 'примеры': urls[:2]}
    with open(r'C:\sender\_tmp\agro_%s' % nm, 'w', encoding='utf-8') as f:
        f.write('\n'.join(urls))
        f.flush()
        os.fsync(f.fileno())
    time.sleep(1.3)
    if urls:
        st2, h2, _ = get(urls[1] if len(urls) > 1 else urls[0])
        t = plain(h2)
        P[nm + '_карточка'] = {
            'url': urls[1] if len(urls) > 1 else urls[0], 'status': st2, 'len': len(h2),
            'title': (re.findall(r'<title[^>]*>(.*?)</title>', h2, re.S | re.I) or [''])[0][:110],
            'инн': re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t)[:3],
            'огрн': re.findall(r'ОГРН[:\s]*(\d{13}|\d{15})', t)[:3],
            'хосты': sorted({x: 1 for x in re.findall(r'href="https?://([^/"?]+)', h2)}.keys())[:14],
            'сайт_ctx': [t[max(0, m.start() - 80):m.start() + 160]
                         for m in list(re.finditer(r'[Сс]айт', t))[:3]]}
        time.sleep(1.3)
# 3. checko: 12 подряд карточек, прямо, пауза 1.5с
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
ogrns = cx.execute("""SELECT inn, ogrn, substr(name,1,30), CAST(revenue_rub AS REAL)
  FROM companies WHERE COALESCE(site,'')='' AND COALESCE(cand_site,'')=''
    AND COALESCE(ogrn,'')!='' AND COALESCE(revenue_rub,'') NOT IN ('','0')
  ORDER BY CAST(revenue_rub AS REAL) DESC LIMIT 12""").fetchall()
cx.close()
res = []
for inn, ogrn, nm, rev in ogrns:
    st, h, dt = get('https://checko.ru/company/%s' % ogrn)
    t = plain(h)
    i = t.find('Веб-сайты')
    sites = ''
    if i >= 0:
        seg = t[i + len('Веб-сайты'):i + 200]
        seg = re.split(r'Cоциальные сети|Социальные сети|Нашли ошибку', seg)[0]
        sites = ' '.join(re.findall(r'\b[a-z0-9][a-z0-9\-.]*\.[a-z]{2,6}\b', seg))[:120]
    res.append({'inn': inn, 'name': nm, 'st': st, 'сек': round(dt, 1), 'len': len(h),
                'блок': i >= 0, 'сайты': sites,
                'блок_кф': bool(re.search(r'(?i)just a moment|captcha|Доступ ограничен', h[:4000]))})
    time.sleep(1.5)
P['checko_серия'] = res
O['пробы'] = P
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['recon6'] = O
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(O, ensure_ascii=False)[:5900])
