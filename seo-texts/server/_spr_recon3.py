# -*- coding: utf-8 -*-
"""Разведка 3: checko по ОГРН — есть ли сайт на карточке; тип источников o-zavodah/agrobase."""
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
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
O['requisites'] = dict(zip(
    ['всего', 'site_checko', 'phones_checko', 'emails_checko', 'okved_all_checko'],
    cx.execute("""SELECT COUNT(*), SUM(COALESCE(site_checko,'')!=''),
      SUM(COALESCE(phones_checko,'')!=''), SUM(COALESCE(emails_checko,'')!=''),
      SUM(COALESCE(okved_all_checko,'')!='') FROM requisites""").fetchone()))
O['req_src'] = cx.execute("SELECT src, COUNT(*) FROM requisites GROUP BY src").fetchall()[:10]
# КДВ и Бобровский
for inn in ('7017094419', '3602011132'):
    r = cx.execute("SELECT inn,name,ogrn,region,revenue_rub,site,cand_site,site_checko "
                   "FROM companies WHERE inn=?", (inn,)).fetchone()
    O.setdefault('контроль', {})[inn] = r
# топ безсайтовых по выручке — для примеров
O['топ_безсайтовых'] = cx.execute("""
  SELECT inn, ogrn, name, region, CAST(revenue_rub AS REAL)
  FROM companies WHERE COALESCE(site,'')='' AND COALESCE(cand_site,'')=''
    AND COALESCE(ogrn,'')!='' AND COALESCE(revenue_rub,'') NOT IN ('','0')
  ORDER BY CAST(revenue_rub AS REAL) DESC LIMIT 6""").fetchall()
cx.close()

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')


def get(url, tmo=35):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,*/*'})
    try:
        with urllib.request.urlopen(req, timeout=tmo) as r:
            raw = r.read()
            enc = 'utf-8'
            m = re.search(r'charset=([\w-]+)', r.headers.get('Content-Type', ''))
            if m:
                enc = m.group(1)
            return r.status, raw.decode(enc, 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace')
        except Exception:
            return e.code, ''
    except Exception as e:
        return -1, str(e)[:120]


def anal(html):
    d = {}
    d['title'] = (re.findall(r'<title[^>]*>(.*?)</title>', html, re.S | re.I) or [''])[0][:120]
    txt = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S | re.I)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt)
    d['инн_в_тексте'] = re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', txt)[:5]
    d['огрн_в_тексте'] = re.findall(r'ОГРН[:\s]*(\d{13}|\d{15})', txt)[:5]
    hosts = {}
    for h in re.findall(r'href="https?://([^/"?]+)', html):
        hosts[h] = hosts.get(h, 0) + 1
    d['внешние_хосты'] = sorted(hosts.items(), key=lambda x: -x[1])[:14]
    for m in re.finditer(r'(?:Сайт|сайт|Веб-сайт|website)', txt):
        d.setdefault('контекст_сайт', []).append(txt[max(0, m.start() - 90):m.start() + 200])
        if len(d['контекст_сайт']) >= 4:
            break
    return d


P = {}
# 1. checko по ОГРН — КДВ ГРУПП
for name, ogrn in [('kdv', '1027000905645'), ('bobrov_check', '')]:
    if not ogrn:
        continue
    st, h = get('https://checko.ru/company/%s' % ogrn)
    P['checko_' + name] = {'status': st, 'len': len(h), **(anal(h) if st == 200 else {})}
    time.sleep(1.5)
# 2. o-zavodah карточка
st, h = get('https://o-zavodah.ru/zavody/ooo-bobrovskii-syrzavod/')
P['ozav_card'] = {'status': st, 'len': len(h), **(anal(h) if st == 200 else {})}
time.sleep(1.2)
# 3. o-zavodah sitemap
st, h = get('https://o-zavodah.ru/sitemap.xml')
P['ozav_sitemap'] = {'status': st, 'len': len(h), 'head': h[:900]}
time.sleep(1.2)
# 4. agrobase карточка
st, h = get('https://www.agrobase.ru/organizations/manufacturer/'
            'pdmanufacturer_97505953-cdd2-489a-b9f7-94fbb43f501e')
P['agro_card'] = {'status': st, 'len': len(h), **(anal(h) if st == 200 else {})}
time.sleep(1.2)
st, h = get('https://www.agrobase.ru/robots.txt')
P['agro_robots'] = {'status': st, 'текст': h[:1200]}
time.sleep(1.2)
st, h = get('https://www.agrobase.ru/sitemap.xml')
P['agro_sitemap'] = {'status': st, 'len': len(h), 'head': h[:900]}
O['пробы'] = P

os.makedirs(r'C:\sender\_tmp', exist_ok=True)
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['recon3'] = O
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(O, ensure_ascii=False)[:5900])
