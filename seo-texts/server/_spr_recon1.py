# -*- coding: utf-8 -*-
"""Разведка 1: состояние базы + что отдаёт checko/o-zavodah/agrobase по одной карточке."""
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
OUT = {}

cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
tabs = [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")]
OUT['таблицы'] = tabs
cols = {}
for t in tabs:
    try:
        cols[t] = [r[1] for r in cx.execute('PRAGMA table_info(%s)' % t)]
    except Exception as e:
        cols[t] = 'err ' + str(e)[:40]
OUT['колонки'] = cols
cnt = {}
for t in tabs:
    try:
        cnt[t] = cx.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]
    except Exception:
        cnt[t] = -1
OUT['строк'] = cnt
try:
    OUT['стадии'] = cx.execute(
        "SELECT stage, COUNT(*) FROM stage_log GROUP BY stage ORDER BY 2 DESC").fetchall()
except Exception as e:
    OUT['стадии'] = str(e)[:80]
try:
    OUT['companies_срез'] = dict(zip(
        ['всего', 'с_site', 'с_cand_site', 'без_обоих', 'с_выручкой',
         'без_сайта_с_выручкой', 'с_ogrn'],
        cx.execute("""SELECT COUNT(*),
          SUM(site IS NOT NULL AND site!=''),
          SUM(cand_site IS NOT NULL AND cand_site!=''),
          SUM(COALESCE(site,'')='' AND COALESCE(cand_site,'')=''),
          SUM(COALESCE(revenue_rub,'') NOT IN ('','0')),
          SUM(COALESCE(site,'')='' AND COALESCE(cand_site,'')='' AND COALESCE(revenue_rub,'') NOT IN ('','0')),
          SUM(COALESCE(ogrn,'')!='')
          FROM companies""").fetchone()))
except Exception as e:
    OUT['companies_срез'] = str(e)[:200]
# пример detail стадии checko
try:
    OUT['checko_detail_примеры'] = cx.execute(
        "SELECT inn, substr(detail,1,120) FROM stage_log WHERE stage='checko' LIMIT 3").fetchall()
except Exception as e:
    OUT['checko_detail_примеры'] = str(e)[:80]
cx.close()

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')


def get(url, tmo=30):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,*/*'})
    try:
        with urllib.request.urlopen(req, timeout=tmo) as r:
            raw = r.read()
            enc = 'utf-8'
            ct = r.headers.get('Content-Type', '')
            m = re.search(r'charset=([\w-]+)', ct)
            if m:
                enc = m.group(1)
            return r.status, raw.decode(enc, 'replace'), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace'), dict(e.headers)
        except Exception:
            return e.code, '', {}
    except Exception as e:
        return -1, str(e)[:120], {}


probes = {
    'checko_robots': 'https://checko.ru/robots.txt',
    'checko_kdv': 'https://checko.ru/company/7017094419',
    'ozav_robots': 'https://o-zavodah.ru/robots.txt',
    'ozav_card': 'https://o-zavodah.ru/zavody/ooo-bobrovskii-syrzavod/',
    'agro_robots': 'https://www.agrobase.ru/robots.txt',
    'agro_card': ('https://www.agrobase.ru/organizations/manufacturer/'
                  'pdmanufacturer_97505953-cdd2-489a-b9f7-94fbb43f501e'),
}
res = {}
for k, u in probes.items():
    st, html, hd = get(u)
    d = {'status': st, 'len': len(html)}
    if k.endswith('robots'):
        d['текст'] = html[:1500]
    else:
        d['title'] = (re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I) or
                      [None, ''])[1][:150] if '<title' in html.lower() else ''
        # ищем ИНН, ОГРН, ссылки наружу
        d['инн_на_стр'] = list(dict.fromkeys(re.findall(r'\b\d{10}\b|\b\d{12}\b', html)))[:12]
        d['слово_ИНН'] = 'ИНН' in html
        d['слово_ОГРН'] = 'ОГРН' in html
        d['слово_сайт'] = bool(re.search(r'[Сс]айт|[Вв]еб-?сайт|website', html))
        # внешние ссылки
        hosts = {}
        for h in re.findall(r'href="https?://([^/"?]+)', html):
            hosts[h] = hosts.get(h, 0) + 1
        d['внешние_хосты'] = sorted(hosts.items(), key=lambda x: -x[1])[:20]
        # контекст вокруг слова Сайт
        for m in re.finditer(r'[Сс]айт', html):
            frag = re.sub(r'\s+', ' ', html[max(0, m.start() - 200):m.start() + 400])
            d.setdefault('контекст_сайт', []).append(frag[:500])
            if len(d['контекст_сайт']) >= 3:
                break
    res[k] = d
    time.sleep(1.2)
OUT['пробы'] = res

os.makedirs(r'C:\sender\_tmp', exist_ok=True)
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump({'recon1': OUT}, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(OUT, ensure_ascii=False)[:5800])
