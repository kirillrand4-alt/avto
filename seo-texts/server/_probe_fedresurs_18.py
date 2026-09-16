# -*- coding: utf-8 -*-
"""Проба 18: вытащить из шаблона договора и памятки оператора условия ОПЛАТЫ
договорного «Сервиса получения сведений». Пробуем несколько кодировок."""
import io, re, sys, ssl, zlib
import urllib.request, urllib.error, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'


def get(u):
    try:
        r = OP.open(urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': '*/*',
                                                       'Referer': 'https://fedresurs.ru/'}),
                    timeout=90)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, b''
    except Exception as e:
        return 0, repr(e)[:110].encode()


KEY = re.compile(r'(плат|тариф|стоимост|вознагражд|оплат|безвозмезд|бесплатн|рубл)', re.I)


def kusochki(txt, tag):
    txt = re.sub(r'\s+', ' ', txt)
    seen, n = set(), 0
    for m in KEY.finditer(txt):
        a, z = max(0, m.start() - 200), min(len(txt), m.end() + 260)
        frag = txt[a:z].strip()
        k = frag[:50]
        if k in seen:
            continue
        seen.add(k)
        n += 1
        if n > 12:
            break
        print('  [%s] ... %s' % (tag, frag[:420]))
    if not n:
        print('  [%s] упоминаний платы не найдено (символов %d)' % (tag, len(txt)))


print('===== A. ШАБЛОН ДОГОВОРА (.doc) =====')
u = 'https://fedresurs.ru/helps/Sfacts/' + urllib.parse.quote(
    'Федресурс.  Договор. Сервис получения сведений.doc')
c, b = get(u)
print('code=%s len=%s' % (c, len(b)))
if c == 200:
    for enc in ('utf-16-le', 'cp1251'):
        try:
            t = b.decode(enc, 'replace')
        except Exception:
            continue
        kir = len(re.findall(r'[а-яА-ЯёЁ]', t))
        print(' -- кодировка %s: кириллицы %d символов' % (enc, kir))
        if kir > 500:
            kusochki(re.sub(r'[^Ѐ-ӿ\w\s.,:;№()%«»-]+', ' ', t), enc)

print('\n===== B. ПАМЯТКА ЕФРСФДЮЛ (PDF) — сырой поиск по потокам =====')
u = 'https://fedresurs.ru/helps/Sfacts/' + urllib.parse.quote(
    'Федресурс. Памятка. Сервис получения сведений.pdf')
c, b = get(u)
print('code=%s len=%s' % (c, len(b)))
if c == 200:
    parts = []
    for m in re.finditer(rb'stream\r?\n(.*?)endstream', b, re.S):
        try:
            parts.append(zlib.decompress(m.group(1)))
        except Exception:
            pass
    raw = b' '.join(parts)
    print('  распаковано байт: %d' % len(raw))
    for enc in ('cp1251', 'utf-16-be', 'utf-8'):
        t = raw.decode(enc, 'replace')
        kir = len(re.findall(r'[а-яА-ЯёЁ]', t))
        print('  -- %s: кириллицы %d' % (enc, kir))
    # шестнадцатеричные строки <...> в PDF нередко UTF-16BE
    hexes = re.findall(rb'<([0-9A-Fa-f]{8,})>', raw)
    if hexes:
        t = b''.join(bytes.fromhex(h.decode()) for h in hexes[:4000]).decode('utf-16-be', 'replace')
        print('  -- hex-строки: кириллицы %d' % len(re.findall(r'[а-яА-ЯёЁ]', t)))
        if len(re.findall(r'[а-яА-ЯёЁ]', t)) > 200:
            kusochki(t, 'pdf-hex')

print('\n===== C. Правила оператора (CurrentRules.pdf) =====')
c, b = get('https://fedresurs.ru/helps/CurrentRules.pdf')
print('code=%s len=%s' % (c, len(b)))
if c == 200:
    parts = []
    for m in re.finditer(rb'stream\r?\n(.*?)endstream', b, re.S):
        try:
            parts.append(zlib.decompress(m.group(1)))
        except Exception:
            pass
    raw = b' '.join(parts)
    hexes = re.findall(rb'<([0-9A-Fa-f]{8,})>', raw)
    t = ''
    if hexes:
        t = b''.join(bytes.fromhex(h.decode()) for h in hexes[:8000]).decode('utf-16-be', 'replace')
    kir = len(re.findall(r'[а-яА-ЯёЁ]', t))
    print('  hex-строк %d, кириллицы %d' % (len(hexes), kir))
    if kir > 200:
        kusochki(t, 'rules')
    else:
        t2 = raw.decode('cp1251', 'replace')
        print('  cp1251 кириллицы %d' % len(re.findall(r'[а-яА-ЯёЁ]', t2)))
        kusochki(t2, 'rules-cp1251')
print('\n==== КОНЕЦ ПРОБЫ 18 ====')
