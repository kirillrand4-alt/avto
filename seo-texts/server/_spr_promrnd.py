# -*- coding: utf-8 -*-
"""Разведка promrnd.ru по той же рамке: robots, sitemap, шаблон карточки,
пагинация, HTML/JS, логин/капча, ИНН и сайт на карточке."""
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
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,*/*'}), timeout=tmo) as r:
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


def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&quot;', '"'), ('&mdash;', '—'), ('&amp;', '&'),
                 ('&laquo;', '"'), ('&raquo;', '"'), ('&ndash;', '-')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


СВОИ = ('promrnd.ru', 'mc.yandex.ru', 'yandex.ru', 'googletagmanager.com', 'vk.com',
        'ok.ru', 't.me', 'youtube.com', 'google.com', 'gstatic.com', 'googleapis.com',
        'egrul.nalog.ru', 'rusprofile.ru', 'checko.ru', 'wa.me', 'gosuslugi.ru')


def чужие(h):
    out = []
    for u in re.findall(r'href="(https?://[^"\s]+)"', h):
        try:
            host = u.split('/', 3)[2].lower()
        except IndexError:
            continue
        if host.startswith('www.'):
            host = host[4:]
        if any(host == s or host.endswith('.' + s) for s in СВОИ):
            continue
        if host not in out:
            out.append(host)
    return out[:6]


R = {}
st, h, dt = get('https://promrnd.ru/robots.txt')
R['robots'] = {'st': st, 'текст': h[:1400]}
time.sleep(1.3)
for nm in ('sitemap.xml', 'sitemap_index.xml'):
    st, h, dt = get('https://promrnd.ru/' + nm)
    R['sm_' + nm] = {'st': st, 'КБ': len(h) // 1024, 'loc': h.count('<loc>'),
                     'индекс': '<sitemapindex' in h, 'head': h[:500]}
    time.sleep(1.3)
# карточка-образец
st, h, dt = get('https://promrnd.ru/company/33/')
t = plain(h)
R['карточка_33'] = {
    'st': st, 'КБ': len(h) // 1024, 'сек': dt,
    'title': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0][:110],
    'инн': re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t)[:3],
    'огрн': re.findall(r'ОГРН[:\s]*(\d{13}|\d{15})', t)[:3],
    'чужие_хосты': чужие(h),
    'сайт_ctx': [t[max(0, m.start() - 90):m.start() + 170]
                 for m in list(re.finditer(r'[Сс]айт', t))[:3]],
    'признак_JS': ('__NUXT__' in h or 'window.__' in h or '<div id="app"' in h),
    'маркеры_саморег': [w for w in ('Добавить компанию', 'добавить организац', 'Регистрация',
                                    'Личный кабинет', 'Это моя компания', 'Войти',
                                    'бесплатно', 'модерац')
                        if w.lower() in t.lower()],
    'фрагмент': t[:600]}
time.sleep(1.4)
# перебор id
пер = {}
for i in (1, 2, 100, 1000, 5000, 20000, 100000):
    st, h, dt = get('https://promrnd.ru/company/%d/' % i)
    t = plain(h)
    пер[i] = {'st': st, 'КБ': len(h) // 1024,
              'title': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0][:60],
              'инн': (re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t) or [''])[0]}
    time.sleep(1.3)
R['перебор_id'] = пер
# списки
for u in ('https://promrnd.ru/', 'https://promrnd.ru/company/',
          'https://promrnd.ru/companies/'):
    st, h, dt = get(u)
    R.setdefault('списки', {})[u] = {
        'st': st, 'КБ': len(h) // 1024,
        'ссылок_на_карточки': len(set(re.findall(r'/company/(\d+)/', h))),
        'page_в_html': sorted({int(x) for x in re.findall(r'[?&/]page[=/](\d{1,5})', h)})[:8],
        'счётчики': re.findall(r'[^.]{0,60}(?:компан|предприят)[^.]{0,40}', plain(h))[:3]}
    time.sleep(1.3)
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['promrnd'] = R
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(R, ensure_ascii=False)[:5700])
