# -*- coding: utf-8 -*-
"""Техкарта 3: списковые страницы agrobase по регионам России и их пагинация."""
import io
import json
import os
import re
import sys
import time
import urllib.request

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


def карт(h):
    return (len(set(re.findall(r'/organizations/apk/organization_apk_\d+', h))),
            len(set(re.findall(r'/organizations/manufacturer/pdmanufacturer_[0-9a-f-]+', h))))


R = {}
st, h = get('https://www.agrobase.ru/organizations')
рос = sorted({u for u in re.findall(r'href="(/organizations/rossiya[^"?#]*)"', h)})
R['россия_пути'] = рос[:12]
R['всего_путей_россия'] = len(рос)
if not рос:
    R['все_пути_образец'] = sorted({u for u in re.findall(r'href="(/organizations/[^"?#]*)"', h)})[-25:]
time.sleep(1.3)
# из sitemap_locations возьмём российские списковые
st, h = get('https://www.agrobase.ru/sitemap_locations.xml')
locs = re.findall(r'<loc>([^<]+)</loc>', h)
R['locations_всего'] = len(locs)
R['locations_образец'] = locs[:6]
time.sleep(1.3)
цели = [u for u in locs if 'oblast' in u or 'kray' in u or 'kraj' in u][:2]
for u in цели:
    st, h = get(u)
    a, m = карт(h)
    стр = sorted({int(x) for x in re.findall(r'[?&]page=(\d{1,4})', h)})
    R.setdefault('списки', {})[u] = {'st': st, 'КБ': len(h) // 1024, 'apk': a, 'manuf': m,
                                     'номера_страниц_в_html': стр[:12]}
    time.sleep(1.3)
    if стр:
        u2 = u + ('&' if '?' in u else '?') + 'page=2'
        st2, h2 = get(u2)
        a2, m2 = карт(h2)
        R['списки'][u]['стр2'] = {'st': st2, 'apk': a2, 'manuf': m2, 'КБ': len(h2) // 1024}
        time.sleep(1.3)
        u3 = u + ('&' if '?' in u else '?') + 'page=9999'
        st3, h3 = get(u3)
        a3, m3 = карт(h3)
        R['списки'][u]['стр9999'] = {'st': st3, 'apk': a3, 'manuf': m3, 'КБ': len(h3) // 1024}
        time.sleep(1.3)
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['tehkarta3'] = R
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(R, ensure_ascii=False)[:5600])
