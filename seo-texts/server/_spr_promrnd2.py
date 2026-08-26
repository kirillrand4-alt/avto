# -*- coding: utf-8 -*-
"""promrnd.ru: robots целиком + полный съём каталога (id из /company/ и перебор
до первого длинного провала). Резюмируемо, jsonl с fsync.
Запуск: python _spr_promrnd2.py sbor | без argv — только robots."""
import io
import json
import os
import random
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')
OUT = r'C:\sender\_tmp\promrnd_cards.jsonl'
СВОИ = ('promrnd.ru', 'mc.yandex.ru', 'yandex.ru', 'googletagmanager.com', 'vk.com',
        'ok.ru', 't.me', 'youtube.com', 'google.com', 'gstatic.com', 'googleapis.com',
        'egrul.nalog.ru', 'rusprofile.ru', 'checko.ru', 'wa.me', 'gosuslugi.ru',
        'cloudflare.com', 'cdnjs.cloudflare.com', 'rostov-gorod.ru', 'frprf.ru',
        'frp61.ru', 'rmfpp.ru', 'donland.ru', 'jquery.com')


def get(url, tmo=35):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,*/*'}), timeout=tmo) as r:
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
                 ('&laquo;', '"'), ('&raquo;', '"')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


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
    return out[:5]


if len(sys.argv) < 2:
    st, h = get('https://promrnd.ru/robots.txt')
    print(json.dumps({'robots_st': st, 'robots': h[:2000]}, ensure_ascii=False))
    sys.exit(0)

st, h = get('https://promrnd.ru/company/')
ids = sorted({int(x) for x in re.findall(r'/company/(\d+)/', h)})
print('из каталога id:', len(ids), 'макс', max(ids) if ids else 0, flush=True)
все = sorted(set(ids) | set(range(1, (max(ids) if ids else 0) + 60)))
done = set()
if os.path.exists(OUT):
    for ln in io.open(OUT, encoding='utf-8', errors='replace'):
        try:
            done.add(json.loads(ln)['id'])
        except Exception:
            pass
f = io.open(OUT, 'a', encoding='utf-8')
n, беды = 0, 0
for i in все:
    if i in done:
        continue
    time.sleep(1.15 + random.random() * 0.3)
    st, h = get('https://promrnd.ru/company/%d/' % i)
    if st in (429, 403, 503):
        беды += 1
        time.sleep(20 * беды)
        if беды >= 5:
            print('promrnd закрывается, отступаю', flush=True)
            break
        continue
    беды = 0
    rec = {'id': i, 'st': st}
    if st == 200:
        t = plain(h)
        rec.update({
            'name': (re.findall(r'<title[^>]*>(.*?)</title>', h, re.S) or [''])[0][:110],
            'inn': (re.findall(r'ИНН[:\s]*(\d{10}|\d{12})', t) or [''])[0],
            'ogrn': (re.findall(r'ОГРН[:\s]*(\d{13}|\d{15})', t) or [''])[0],
            'ext': чужие(h),
            'на_портале_с': (re.findall(r'На портале с\s*([\d.]{8,10})', t) or [''])[0],
            'email': (re.findall(r'[\w.\-+]+@[\w.\-]+\.[a-z]{2,6}', t) or [''])[0][:50],
            'phone': (re.findall(r'\+?7[\d\s\-()]{9,18}', t) or [''])[0][:20]})
    n += 1
    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    if n % 25 == 0:
        f.flush()
        os.fsync(f.fileno())
        print('promrnd', n, flush=True)
f.flush()
os.fsync(f.fileno())
f.close()
print('promrnd ГОТОВО', n, flush=True)
