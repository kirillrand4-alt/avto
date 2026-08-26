# -*- coding: utf-8 -*-
"""Разведка 4: кто писал site_checko (register_checko.cs), o-zavodah с кукой, каталоги."""
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
# 1. Ищем register_checko.cs и его код
for base in (r'C:\sender\server', r'C:\sender'):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d.lower() not in ('node_modules', '.git', '_tmp', 'venv')]
        for fn in files:
            if 'checko' in fn.lower():
                O.setdefault('файлы_checko', []).append(os.path.join(root, fn))
    if len(O.get('файлы_checko') or []) > 40:
        break
O['файлы_checko'] = (O.get('файлы_checko') or [])[:30]
for p in O['файлы_checko']:
    if p.lower().endswith('.cs'):
        try:
            src = open(p, encoding='utf-8', errors='replace').read()
            O.setdefault('cs_фрагменты', {})[os.path.basename(p)] = {
                'len': len(src),
                'site_упоминания': [re.sub(r'\s+', ' ', src[max(0, m.start() - 200):m.start() + 260])
                                    for m in list(re.finditer(r'[Сс]айт|site', src))[:6]],
            }
        except Exception as e:
            O.setdefault('cs_фрагменты', {})[os.path.basename(p)] = str(e)[:60]

cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
O['requisites'] = dict(zip(
    ['всего', 'site_checko', 'phones_checko', 'emails_checko', 'okved_all_checko'],
    cx.execute("""SELECT COUNT(*), SUM(COALESCE(site_checko,'')!=''),
      SUM(COALESCE(phones_checko,'')!=''), SUM(COALESCE(emails_checko,'')!=''),
      SUM(COALESCE(okved_all_checko,'')!='') FROM requisites""").fetchone()))
O['req_src'] = cx.execute("SELECT src, COUNT(*) FROM requisites GROUP BY src").fetchall()[:10]
O['контроль'] = {}
for inn in ('7017094419', '3602011132', '2348023360'):
    O['контроль'][inn] = cx.execute(
        "SELECT inn,name,ogrn,region,revenue_rub,COALESCE(site,''),COALESCE(cand_site,'') "
        "FROM companies WHERE inn=?", (inn,)).fetchone()
O['топ_безсайтовых'] = cx.execute("""
  SELECT inn, ogrn, substr(name,1,40), CAST(revenue_rub AS REAL)
  FROM companies WHERE COALESCE(site,'')='' AND COALESCE(cand_site,'')=''
    AND COALESCE(ogrn,'')!='' AND COALESCE(revenue_rub,'') NOT IN ('','0')
  ORDER BY CAST(revenue_rub AS REAL) DESC LIMIT 5""").fetchall()
cx.close()

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')


def get(url, tmo=35, cookie=''):
    hd = {'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
          'Accept': 'text/html,application/xhtml+xml,*/*'}
    if cookie:
        hd['Cookie'] = cookie
    req = urllib.request.Request(url, headers=hd)
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


P = {}
CK = 'beget=begetok'
st, h = get('https://o-zavodah.ru/zavody/ooo-bobrovskii-syrzavod/', cookie=CK)
txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(
    r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)))
P['ozav_card'] = {'status': st, 'len': len(h),
                  'title': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S | re.I) or [''])[0][:120],
                  'инн': re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', txt)[:4],
                  'огрн': re.findall(r'ОГРН[:\s]*(\d{13}|\d{15})', txt)[:4],
                  'хосты': sorted({x: 1 for x in re.findall(r'href="https?://([^/"?]+)', h)}.keys())[:20],
                  'сайт_контекст': [txt[max(0, m.start() - 100):m.start() + 200]
                                    for m in list(re.finditer(r'[Сс]айт', txt))[:4]]}
time.sleep(1.2)
st, h = get('https://o-zavodah.ru/sitemap.xml', cookie=CK)
P['ozav_sitemap'] = {'status': st, 'len': len(h), 'head': h[:800]}
time.sleep(1.2)
st, h = get('https://www.agrobase.ru/sitemap_manufacturers.xml')
P['agro_sm_manuf'] = {'status': st, 'len': len(h), 'n_loc': h.count('<loc>'),
                      'head': h[:400], 'index': '<sitemapindex' in h}
O['пробы'] = P

try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['recon4'] = O
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(O, ensure_ascii=False)[:5900])
