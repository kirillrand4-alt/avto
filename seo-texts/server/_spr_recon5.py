# -*- coding: utf-8 -*-
"""Разведка 5: масштабы каталогов + checko-карточка КДВ + код checko_contacts.py."""
import io
import json
import os
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
O = {}
p = r'C:\sender\server\ops\checko_contacts.py'
try:
    src = open(p, encoding='utf-8', errors='replace').read()
    O['checko_contacts_len'] = len(src)
    O['checko_contacts_head'] = src[:2200]
except Exception as e:
    O['checko_contacts_head'] = str(e)[:80]

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')


def get(url, tmo=40, cookie=''):
    hd = {'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
          'Accept': 'text/html,application/xhtml+xml,*/*'}
    if cookie:
        hd['Cookie'] = cookie
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=tmo) as r:
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


CK = 'beget=begetok'
P = {}
# o-zavodah: размер каталога
st, h = get('https://o-zavodah.ru/sitemap.xml', cookie=CK)
locs = re.findall(r'<loc>([^<]+)</loc>', h)
pref = {}
for u in locs:
    seg = u.replace('https://o-zavodah.ru/', '').split('/')[0]
    pref[seg] = pref.get(seg, 0) + 1
P['ozav'] = {'всего_url': len(locs),
             'по_разделам': sorted(pref.items(), key=lambda x: -x[1])[:12],
             'zavody_url': sum(1 for u in locs if '/zavody/' in u),
             'примеры_zavody': [u for u in locs if '/zavody/' in u][:3],
             'есть_ли_другие_sitemap': '<sitemapindex' in h}
os.makedirs(r'C:\sender\_tmp', exist_ok=True)
with open(r'C:\sender\_tmp\ozav_sitemap.xml', 'w', encoding='utf-8') as f:
    f.write(h)
    f.flush()
    os.fsync(f.fileno())
time.sleep(1.2)
# agrobase: полный индекс
st, h = get('https://www.agrobase.ru/sitemap.xml')
sms = re.findall(r'<loc>([^<]+)</loc>', h)
P['agro_index'] = sms
cnt = {}
for u in sms:
    time.sleep(1.2)
    st2, h2 = get(u)
    n = h2.count('<loc>')
    cnt[u.rsplit('/', 1)[-1]] = {'status': st2, 'n': n}
    if 'manufacturer' in u or 'organization' in u or 'seller' in u or 'dealer' in u:
        with open(r'C:\sender\_tmp\agro_%s' % u.rsplit('/', 1)[-1], 'w', encoding='utf-8') as f:
            f.write(h2)
            f.flush()
            os.fsync(f.fileno())
P['agro_sitemaps'] = cnt
# checko: карточка КДВ по ОГРН из нашей базы
time.sleep(1.5)
st, h = get('https://checko.ru/company/1047000131001')
txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(
    r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)))
i = txt.find('Веб-сайт')
P['checko_kdv'] = {'status': st, 'len': len(h),
                   'title': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S | re.I) or [''])[0][:110],
                   'есть_Веб-сайты': i >= 0,
                   'фрагмент': txt[max(0, i - 300):i + 320] if i >= 0 else txt[:300],
                   'хосты': sorted({x: 1 for x in re.findall(r'href="https?://([^/"?]+)', h)}.keys())[:15]}
O['пробы'] = P
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['recon5'] = O
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(O, ensure_ascii=False)[:5900])
