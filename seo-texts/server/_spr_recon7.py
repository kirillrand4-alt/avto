# -*- coding: utf-8 -*-
"""Разведка 7: серия checko + правило извлечения сайта на agrobase/o-zavodah."""
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
СВОИ = ('agrobase.ru', 'agroserver.ru', 'createit.ru', 'fonts.googleapis.com',
        'fonts.gstatic.com', 'o-zavodah.ru', 'mc.yandex.ru', 'googletagmanager.com',
        'yandex.ru', 'egrul.nalog.ru', 'gks.ru', 'vk.com', 'ok.ru', 't.me',
        'youtube.com', 'checko.ru', 'yastatic.net', 'chrome.google.com',
        'декларации-соответствия.рус', 'zakupki.gov.ru', 'kad.arbitr.ru',
        'trudvsem.ru', 'fips.ru', 'an.yandex.ru')


def get(url, tmo=40, cookie=''):
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
            return r.status, raw.decode(enc, 'replace'), round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace'), round(time.time() - t0, 1)
        except Exception:
            return e.code, '', round(time.time() - t0, 1)
    except Exception as e:
        return -1, str(e)[:100], round(time.time() - t0, 1)


def plain(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(
        r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)))


def чужие(h):
    out = []
    for u in re.findall(r'href="(https?://[^"]+)"', h):
        host = u.split('/', 3)[2].lower().lstrip('www.')
        if any(host == s or host.endswith('.' + s) for s in СВОИ):
            continue
        if host not in out:
            out.append(host)
    return out[:6]


R = {}
# --- checko серия
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
rows = cx.execute("""SELECT inn, ogrn, substr(name,1,26), CAST(revenue_rub AS REAL)
  FROM companies WHERE COALESCE(site,'')='' AND COALESCE(cand_site,'')=''
    AND COALESCE(ogrn,'')!='' AND COALESCE(revenue_rub,'') NOT IN ('','0')
  ORDER BY CAST(revenue_rub AS REAL) DESC LIMIT 14""").fetchall()
cx.close()
ser = []
for inn, ogrn, nm, rev in rows:
    st, h, dt = get('https://checko.ru/company/%s' % ogrn)
    t = plain(h)
    i = t.find('Веб-сайты')
    s = ''
    if i >= 0:
        seg = re.split(r'C?оциальные сети|Нашли ошибку', t[i + 9:i + 220])[0]
        s = ' '.join(re.findall(r'\b[a-zа-я0-9][a-zа-я0-9\-.]*\.[a-zа-я]{2,6}\b', seg))[:90]
    ser.append([inn, nm, st, dt, len(h), s or ('—' if i >= 0 else 'НЕТ БЛОКА'),
                'CF' if re.search(r'(?i)just a moment|captcha', h[:3000]) else ''])
    time.sleep(1.5)
R['checko_серия'] = ser

# --- agrobase: 4 manufacturer + 3 apk
try:
    mf = open(r'C:\sender\_tmp\agro_sitemap_dealers.xml', encoding='utf-8').read().split()
except Exception:
    mf = []
st, h, _ = get('https://www.agrobase.ru/sitemap_manufacturers.xml')
mans = re.findall(r'<loc>([^<]+)</loc>', h)
time.sleep(1.3)
ag = []
for u in mans[2:6]:
    st, h, dt = get(u)
    t = plain(h)
    ag.append({'u': u[-14:], 'st': st,
               'nm': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0][:60],
               'инн': (re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t) or [''])[0],
               'огрн': (re.findall(r'ОГРН[:\s]*(\d{13}|\d{15})', t) or [''])[0],
               'чужие': чужие(h)})
    time.sleep(1.3)
R['agro_manuf'] = ag
apk = []
for n in (5, 900, 12000):
    u = 'https://www.agrobase.ru/organizations/apk/organization_apk_%d' % n
    st, h, dt = get(u)
    t = plain(h)
    apk.append({'n': n, 'st': st,
                'nm': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0][:55],
                'инн': (re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t) or [''])[0],
                'чужие': чужие(h),
                'моя_компания': 'это моя компания' in t.lower() or 'Это ваша компания' in t})
    time.sleep(1.3)
R['agro_apk'] = apk

# --- o-zavodah 3 карточки
CK = 'beget=begetok'
st, h, _ = get('https://o-zavodah.ru/sitemap.xml', cookie=CK)
zav = [u for u in re.findall(r'<loc>([^<]+)</loc>', h) if '/zavody/' in u and u.count('/') > 4]
time.sleep(1.3)
oz = []
for u in zav[3:8]:
    st, h, dt = get(u, cookie=CK)
    t = plain(h)
    oz.append({'u': u.rsplit('/', 2)[-2][:26], 'st': st,
               'инн': (re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t) or [''])[0],
               'огрн': (re.findall(r'ОГРН[:\s]*(\d{13}|\d{15})', t) or [''])[0],
               'сайт': (re.findall(r'Официальный сайт:\s*(\S+)', t) or
                        re.findall(r'\bСайт\s+(https?://\S+)', t) or [''])[0][:50],
               'чужие': чужие(h)})
    time.sleep(1.3)
R['ozav'] = oz
R['ozav_всего_карточек'] = len(zav)

try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['recon7'] = R
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(R, ensure_ascii=False)[:5800])
