# -*- coding: utf-8 -*-
"""Техническая карточка источников для сборки кубика в Зенке:
точка входа, шаблон URL, пагинация и её потолок, HTML/JS, логин/капча.
Уважаем robots: на o-zavodah никаких query-строк (там Disallow: /*?*),
на agrobase разрешён только ?page=, на checko не трогаем /search и /company/select."""
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


def get(url, cookie='', tmo=45):
    hd = {'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
          'Accept': 'text/html,application/xhtml+xml,*/*'}
    if cookie:
        hd['Cookie'] = cookie
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=tmo) as r:
            raw = r.read()
            enc = 'utf-8'
            m = re.search(r'charset=([\w-]+)', r.headers.get('Content-Type', ''))
            if m:
                enc = m.group(1)
            return r.status, raw.decode(enc, 'replace'), round(time.time() - t0, 2)
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace'), round(time.time() - t0, 2)
        except Exception:
            return e.code, '', round(time.time() - t0, 2)
    except Exception as e:
        return -1, str(e)[:70], round(time.time() - t0, 2)


R = {}
CK = 'beget=begetok'
# --- o-zavodah: единый индекс, без query
st, h, dt = get('https://o-zavodah.ru/zavody/', cookie=CK)
ссыл = sorted(set(re.findall(r'href="(/zavody/[^"?]+/)"', h)))
R['o-zavodah_индекс'] = {'url': 'https://o-zavodah.ru/zavody/', 'st': st,
                         'КБ': len(h) // 1024, 'сек': dt, 'ссылок_на_карточки': len(ссыл),
                         'пагинация_нужна': False,
                         'признак_JS': 'window.' in h and 'application/ld+json' in h,
                         'кука_нужна': True}
time.sleep(1.3)
# без куки
st2, h2, _ = get('https://o-zavodah.ru/zavody/')
R['o-zavodah_без_куки'] = {'st': st2, 'байт': len(h2), 'это_заглушка': len(h2) < 600}
time.sleep(1.3)
# --- agrobase: пагинация раздела АПК (robots: Allow: *?page=)
ст = {}
for p in (1, 2, 50, 200, 500, 1000, 2000):
    u = 'https://www.agrobase.ru/organizations/apk' + ('' if p == 1 else '?page=%d' % p)
    st, h, dt = get(u)
    карт = sorted(set(re.findall(r'href="(/organizations/apk/organization_apk_\d+)"', h)))
    ст[p] = {'st': st, 'КБ': len(h) // 1024, 'карточек_на_стр': len(карт), 'сек': dt}
    time.sleep(1.3)
R['agrobase_пагинация_АПК'] = ст
st, h, dt = get('https://www.agrobase.ru/organizations/manufacturer')
R['agrobase_раздел_производителей'] = {
    'st': st, 'КБ': len(h) // 1024,
    'карточек': len(set(re.findall(r'href="(/organizations/manufacturer/pdmanufacturer_[0-9a-f-]+)"', h)))}
time.sleep(1.3)
# --- checko: точки входа
for имя, u in (('по_ИНН', 'https://checko.ru/company/7017094419'),
               ('по_ОГРН', 'https://checko.ru/company/1047000131001'),
               ('contacts', 'https://checko.ru/company/1047000131001/contacts'),
               ('api_страница', 'https://checko.ru/api')):
    st, h, dt = get(u)
    R.setdefault('checko_точки', {})[имя] = {
        'st': st, 'КБ': len(h) // 1024, 'сек': dt,
        'title': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0][:80]}
    if имя == 'api_страница' and st == 200:
        t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
        R['checko_точки'][имя]['цены'] = re.findall(
            r'[^.]{0,70}(?:руб|₽|тариф|запрос)[^.]{0,60}', t)[:6]
    time.sleep(1.4)
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['tehkarta'] = R
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(R, ensure_ascii=False)[:5700])
