# -*- coding: utf-8 -*-
"""Съём отраслевых каталогов: o-zavodah.ru и agrobase.ru.

Запуск: python _spr_kat.py <фаза>   фаза = ozav | agro | apk
Без argv — ничего не делает (файл просто заливается на сервер).
Резюмируемо: строки пишутся в jsonl с fsync каждые 25 записей; уже снятые URL
пропускаются. Вежливость: 1.15 с между запросами к одному домену, свой UA,
на 429/403 — экспоненциальный отход и выход после 5 подряд.
"""
import io
import json
import os
import random
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
TMP = r'C:\sender\_tmp'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')
ПАУЗА = 1.15
СВОИ = ('agrobase.ru', 'agroserver.ru', 'createit.ru', 'fonts.googleapis.com',
        'fonts.gstatic.com', 'o-zavodah.ru', 'mc.yandex.ru', 'googletagmanager.com',
        'yandex.ru', 'egrul.nalog.ru', 'gks.ru', 'vk.com', 'ok.ru', 't.me', 'wa.me',
        'youtube.com', 'checko.ru', 'yastatic.net', 'chrome.google.com', 'google.com',
        'zakupki.gov.ru', 'kad.arbitr.ru', 'trudvsem.ru', 'fips.ru', 'an.yandex.ru',
        'rutube.ru', 'dzen.ru', 'instagram.com', 'facebook.com', 'twitter.com',
        'wikipedia.org', 'rusprofile.ru', 'list-org.com', 'zachestnyibiznes.ru')


def свой(host):
    h = host.lower()
    if h.startswith('www.'):
        h = h[4:]
    if 'сертификаты-соответствия' in h or 'декларации-соответствия' in h:
        return True
    return any(h == s or h.endswith('.' + s) for s in СВОИ)


def get(url, cookie='', tmo=35):
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
        return e.code, ''
    except Exception:
        return -1, ''


def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&quot;', '"'), ('&mdash;', '—'), ('&amp;', '&'),
                 ('&#8209;', '-'), ('&ndash;', '-'), ('&laquo;', '"'), ('&raquo;', '"')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


def чужие(h):
    out = []
    for u in re.findall(r'href="(https?://[^"\s]+)"', h):
        try:
            host = u.split('/', 3)[2]
        except IndexError:
            continue
        if свой(host):
            continue
        host = host.lower()
        if host.startswith('www.'):
            host = host[4:]
        if host not in out:
            out.append(host)
    return out[:5]


def писать(f, rec, n):
    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    if n % 25 == 0:
        f.flush()
        os.fsync(f.fileno())


def сделано(path):
    s = set()
    if os.path.exists(path):
        for ln in io.open(path, encoding='utf-8', errors='replace'):
            try:
                s.add(json.loads(ln)['url'])
            except Exception:
                pass
    return s


def фаза_ozav():
    out = os.path.join(TMP, 'ozav_cards.jsonl')
    CK = 'beget=begetok'
    st, h = get('https://o-zavodah.ru/sitemap.xml', cookie=CK)
    urls = [u for u in re.findall(r'<loc>([^<]+)</loc>', h)
            if '/zavody/' in u and u.rstrip('/').count('/') > 3]
    done = сделано(out)
    urls = [u for u in urls if u not in done]
    print('ozav: карточек к съёму', len(urls), 'уже', len(done), flush=True)
    f = io.open(out, 'a', encoding='utf-8')
    n, беды = 0, 0
    for u in urls:
        time.sleep(ПАУЗА + random.random() * 0.3)
        st, h = get(u, cookie=CK)
        if st in (429, 403, 503):
            беды += 1
            time.sleep(20 * беды)
            if беды >= 5:
                print('ozav: источник закрывается, отступаю', flush=True)
                break
            continue
        беды = 0
        if st != 200 or len(h) < 2000:
            n += 1
            писать(f, {'url': u, 'st': st}, n)
            continue
        t = plain(h)
        rec = {'url': u, 'st': st,
               'name': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0].strip()[:160],
               'inn': (re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t) or [''])[0],
               'ogrn': (re.findall(r'ОГРН[:\s]*(\d{13}|\d{15})', t) or [''])[0],
               'site': (re.findall(r'Официальный сайт:\s*(\S+)', t) or [''])[0][:120],
               'phone': (re.findall(r'Телефон\s*(\+7[\d\s\-()]{9,20})', t) or [''])[0].strip(),
               'email': (re.findall(r'[Ээ]лектронная почта\s*([\w.\-+]+@[\w.\-]+)', t) or [''])[0],
               'ext': чужие(h)}
        n += 1
        писать(f, rec, n)
        if n % 250 == 0:
            print('ozav', n, flush=True)
    f.flush()
    os.fsync(f.fileno())
    f.close()
    print('ozav ГОТОВО', n, flush=True)


def _agro_card(u):
    st, h = get(u)
    if st != 200 or len(h) < 3000:
        return {'url': u, 'st': st}
    t = plain(h)
    ttl = (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0].strip()
    reg = (re.findall(r'\(([^()]{4,60})\)', ttl) or [''])[0]
    return {'url': u, 'st': st, 'name': ttl[:160], 'region': reg,
            'inn': (re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t) or [''])[0],
            'ogrn': (re.findall(r'ОГРН[:\s]*(\d{13}|\d{15})', t) or [''])[0],
            'ext': чужие(h),
            'phone': (re.findall(r'(\+7[\d\s\-()]{9,20})', t) or [''])[0].strip()[:22],
            'email': (re.findall(r'[\w.\-+]+@[\w.\-]+\.[a-z]{2,6}', t) or [''])[0][:60]}


def фаза_agro():
    out = os.path.join(TMP, 'agro_cards.jsonl')
    urls = []
    for nm in ('sitemap_manufacturers.xml', 'sitemap_dealers.xml'):
        st, h = get('https://www.agrobase.ru/' + nm)
        for u in re.findall(r'<loc>([^<]+)</loc>', h):
            if u not in urls:
                urls.append(u)
        time.sleep(ПАУЗА)
    done = сделано(out)
    urls = [u for u in urls if u not in done]
    print('agro: карточек к съёму', len(urls), 'уже', len(done), flush=True)
    f = io.open(out, 'a', encoding='utf-8')
    n, беды = 0, 0
    for u in urls:
        time.sleep(ПАУЗА + random.random() * 0.3)
        rec = _agro_card(u)
        if rec.get('st') in (429, 403, 503):
            беды += 1
            time.sleep(20 * беды)
            if беды >= 5:
                print('agro: источник закрывается, отступаю', flush=True)
                break
            continue
        беды = 0
        n += 1
        писать(f, rec, n)
        if n % 250 == 0:
            print('agro', n, flush=True)
    f.flush()
    os.fsync(f.fileno())
    f.close()
    print('agro ГОТОВО', n, flush=True)


def фаза_apk():
    """АПК-раздел: 23682 карточки. Сначала выборка 400 равномерно — измерить долю
    с сайтом; полный съём запускать только если доля оправдывает 8 часов."""
    out = os.path.join(TMP, 'agro_apk_sample.jsonl')
    st, h = get('https://www.agrobase.ru/sitemap_apk.xml')
    urls = re.findall(r'<loc>([^<]+)</loc>', h)
    шаг = max(1, len(urls) // 400)
    выб = urls[::шаг][:400]
    done = сделано(out)
    выб = [u for u in выб if u not in done]
    print('apk: выборка', len(выб), 'из', len(urls), flush=True)
    f = io.open(out, 'a', encoding='utf-8')
    n, беды = 0, 0
    for u in выб:
        time.sleep(ПАУЗА + random.random() * 0.3)
        rec = _agro_card(u)
        if rec.get('st') in (429, 403, 503):
            беды += 1
            time.sleep(20 * беды)
            if беды >= 5:
                break
            continue
        беды = 0
        n += 1
        писать(f, rec, n)
        if n % 100 == 0:
            print('apk', n, flush=True)
    f.flush()
    os.fsync(f.fileno())
    f.close()
    print('apk ГОТОВО', n, flush=True)


if __name__ == '__main__':
    ф = sys.argv[1] if len(sys.argv) > 1 else ''
    if ф == 'ozav':
        фаза_ozav()
    elif ф == 'agro':
        фаза_agro()
    elif ф == 'apk':
        фаза_apk()
    else:
        print(json.dumps({'загружен': True, 'фазы': ['ozav', 'agro', 'apk']},
                         ensure_ascii=False))
