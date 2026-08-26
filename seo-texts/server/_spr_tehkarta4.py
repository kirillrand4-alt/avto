# -*- coding: utf-8 -*-
"""Техкарта 4: российские списковые страницы agrobase, их пагинация и потолок."""
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


def get(url, tmo=45):
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
for имя, u in (('russia', 'https://www.agrobase.ru/organizations/location/locationrussia'),
               ('loc22', 'https://www.agrobase.ru/organizations/location/location22')):
    st, h = get(u)
    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
    a, m = карт(h)
    R[имя] = {'st': st, 'КБ': len(h) // 1024, 'apk': a, 'manuf': m,
              'счётчик': re.findall(r'(?:Россия|Найдено|Всего)[:\s]*([\d\s]{3,12})', t)[:4],
              'слова_пагинации': [w for w in ('Показать ещё', 'Ещё', 'Далее', 'Следующая',
                                              'page=', 'Загрузить') if w in h],
              'page_в_html': sorted({int(x) for x in re.findall(r'[?&]page=(\d{1,5})', h)})[:10]}
    time.sleep(1.4)
    for p in (2, 5, 50, 9999):
        st2, h2 = get(u + '?page=%d' % p)
        a2, m2 = карт(h2)
        R[имя]['page%d' % p] = {'st': st2, 'КБ': len(h2) // 1024, 'apk': a2, 'manuf': m2}
        time.sleep(1.4)
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['tehkarta4'] = R
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(R, ensure_ascii=False)[:5600])
