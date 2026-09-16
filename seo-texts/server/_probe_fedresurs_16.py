# -*- coding: utf-8 -*-
"""Проба 16: ПЛАТНОСТЬ. Официальные документы Федресурса про «Сервис получения
сведений» (договорной API) — вытаскиваем текст и ищем упоминания платы/тарифа.
Плюс справка сайта. Только чтение + печать."""
import io, re, sys, ssl, json, zlib
import urllib.request, urllib.error, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')


def get(u, ref='https://fedresurs.ru/'):
    try:
        r = OP.open(urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': '*/*',
                                                       'Referer': ref}), timeout=60)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b''
    except Exception as e:
        return 0, repr(e)[:120].encode()


def pdf_text(raw):
    """Грубое извлечение текста из PDF: распаковываем потоки и берём строки в скобках."""
    out = []
    for m in re.finditer(rb'stream\r?\n(.*?)endstream', raw, re.S):
        chunk = m.group(1)
        try:
            chunk = zlib.decompress(chunk)
        except Exception:
            continue
        for t in re.findall(rb'\((?:\\.|[^()\\])*\)', chunk):
            s = t[1:-1]
            s = re.sub(rb'\\([()\\])', rb'\1', s)
            try:
                out.append(s.decode('cp1251', 'replace'))
            except Exception:
                pass
    return ' '.join(out)


DOCS = [
    ('ЕФРСФДЮЛ памятка (PDF)',
     'https://fedresurs.ru/helps/Sfacts/' + urllib.parse.quote(
         'Федресурс. Памятка. Сервис получения сведений.pdf')),
    ('ЕФРСБ REST спецификация 1.3.0 (PDF)',
     'https://fedresurs.ru/helps/bankrupt/Service_rest_1.3.0.pdf'),
    ('Важная информация для подключения веб-сервиса (PDF)',
     'https://fedresurs.ru/helps/bankrupt/' + urllib.parse.quote(
         'Важная информация для подключения веб-сервиса.pdf')),
    ('Договор. Сервис получения сведений (DOC)',
     'https://fedresurs.ru/helps/Sfacts/' + urllib.parse.quote(
         'Федресурс.  Договор. Сервис получения сведений.doc')),
]
DENGI = re.compile(r'(плат|тариф|стоимост|вознагражд|руб|цена|безвозмезд|бесплатн|НДС|'
                   r'договор|оплат)', re.I)

for name, u in DOCS:
    c, b = get(u)
    print('\n===== %s =====\ncode=%s len=%s' % (name, c, len(b)))
    if c != 200 or len(b) < 500:
        continue
    if b[:4] == b'%PDF':
        txt = pdf_text(b)
    else:
        txt = b.decode('cp1251', 'replace')
        txt = re.sub(r'[^Ѐ-ӿ\w\s.,:;№()%-]+', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt)
    print('  извлечено символов: %d' % len(txt))
    hits = []
    for m in DENGI.finditer(txt):
        a, z = max(0, m.start() - 160), min(len(txt), m.end() + 200)
        hits.append(txt[a:z])
    seen, n = set(), 0
    for h in hits:
        k = h[:60]
        if k in seen:
            continue
        seen.add(k)
        n += 1
        if n > 10:
            break
        print('   ... %s' % h.strip()[:360])

print('\n===== справка на сайте =====')
for p in ('backend/help', 'backend/settings/help', 'backend/orders/rules'):
    c, b = get('https://fedresurs.ru/' + p)
    t = b.decode('utf-8', 'replace')
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    print('  %-26s code=%s len=%s: %s' % (p, c, len(b), t[:600]))
print('\n==== КОНЕЦ ПРОБЫ 16 ====')
