# -*- coding: utf-8 -*-
"""Техкарта 2: реальные списковые URL agrobase + checko через прокси (наш IP в 429)."""
import io
import json
import os
import re
import sys
import time
import urllib.request

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')


def get(url, tmo=40):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'}), timeout=tmo) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace')
        except Exception:
            return e.code, ''
    except Exception as e:
        return -1, str(e)[:60]


R = {}
st, h = get('https://www.agrobase.ru/organizations')
пути = sorted({u for u in re.findall(r'href="(/[^"?#]*)"', h)
               if 'organization' in u or 'predpr' in u or 'apk' in u})
R['agrobase_organizations'] = {'st': st, 'КБ': len(h) // 1024,
                               'внутренние_пути': пути[:20]}
time.sleep(1.3)
# из sitemap видно шаблон карточек; проверим списковую страницу региона
for u in ('https://www.agrobase.ru/organizations/apk/',
          'https://www.agrobase.ru/organizations/predpriyatiya-apk',
          'https://www.agrobase.ru/organizations?page=2'):
    st, h = get(u)
    R.setdefault('agrobase_пробы_списков', {})[u] = {
        'st': st, 'КБ': len(h) // 1024,
        'карточек_apk': len(set(re.findall(r'/organizations/apk/organization_apk_\d+', h))),
        'карточек_manuf': len(set(re.findall(r'/organizations/manufacturer/pdmanufacturer_[0-9a-f-]+', h)))}
    time.sleep(1.3)
# checko через прокси
d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
req = urllib.request.Request(
    os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
    + '/dolphin-proxies.txt', headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
PX = []
for l in d.open(req, timeout=30).read().decode('utf-8', 'replace').splitlines():
    l = l.strip()
    m = re.match(r'(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', l) if l and not l.startswith('#') else None
    if m:
        u, p, hh, _ = m.groups()
        PX.append('socks5://%s:%s@%s:3001' % (u, p, hh))
for i, (имя, u) in enumerate((('по_ИНН', 'https://checko.ru/company/7017094419'),
                              ('по_ОГРН', 'https://checko.ru/company/1047000131001'),
                              ('contacts', 'https://checko.ru/company/1047000131001/contacts'),
                              ('api', 'https://checko.ru/api'))):
    px = PX[i % len(PX)]
    try:
        r = requests.get(u, headers={'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'},
                         proxies={'http': px, 'https': px}, timeout=30)
        st, h = r.status_code, r.text
    except Exception as e:
        st, h = -1, str(e)[:60]
    d2 = {'st': st, 'КБ': len(h) // 1024,
          'title': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0][:90]}
    if имя == 'api' and st == 200:
        t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
        d2['куски'] = re.findall(r'[^.]{0,80}(?:₽|руб|запрос|тариф|лимит)[^.]{0,70}', t)[:8]
    R.setdefault('checko', {})[имя] = d2
    time.sleep(1.4)
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['tehkarta2'] = R
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(R, ensure_ascii=False)[:5700])
