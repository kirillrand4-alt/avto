# -*- coding: utf-8 -*-
"""ТЭК-Торг: собрать организаторов из листингов посильных секций.
Durable: C:\\seostat\\drop\\drop-storage\\tek_orgs.json (раздаётся дропом).
Резюмируемо: уже собранные (секция,страница) пропускаются."""
import json
import os
import re
import ssl
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
import http.cookiejar as _cj  # noqa: E402
OP = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.HTTPCookieProcessor(_cj.CookieJar()))
B = 'https://www.tektorg.ru'
ФАЙЛ = r'C:\seostat\drop\drop-storage\tek_orgs.json'
БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
НАЧАЛО = time.time()
ЗАДАНИЕ = [('rosneft', 37), ('rosnefttkp', 126), ('tenders', 450)]
if len(sys.argv) > 2:
    ЗАДАНИЕ = [(s, int(n)) for s, n in
               (x.split(':') for x in sys.argv[2].split(','))]

накоп = {}
if os.path.exists(ФАЙЛ):
    try:
        накоп = json.load(open(ФАЙЛ, encoding='utf-8'))
    except Exception:  # noqa: BLE001
        накоп = {}
накоп.setdefault('орг', {})       # имя -> {секция: [ids], n}
накоп.setdefault('стр', [])       # сделанные «секция:страница»
сдел = set(накоп['стр'])
print('СТАРТ ' + json.dumps({'уже_страниц': len(сдел),
                             'уже_организаторов': len(накоп['орг'])}), flush=True)


def lp(h):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h or '', re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(1))
    except Exception:  # noqa: BLE001
        return {}
    return (((d.get('props') or {}).get('pageProps') or {})
            .get('initialReduxState') or {}).get('listingProcedures') or {}


def стр(зад):
    сек, n = зад
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return зад, []
    try:
        r = urllib.request.Request(f'{B}/{сек}/procedures?page={n}', headers={
            'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'})
        with OP.open(r, timeout=35) as f:
            h = EC._раскодировать(f.read(), f.headers.get('Content-Type', ''))
        return зад, (lp(h).get('data') or [])
    except Exception:  # noqa: BLE001
        return зад, []


работа = []
for сек, стрN in ЗАДАНИЕ:
    for n in range(1, стрN + 1):
        if f'{сек}:{n}' not in сдел:
            работа.append((сек, n))
print('к обходу страниц', len(работа), flush=True)
готово = 0
with ThreadPoolExecutor(max_workers=8) as пул:
    for (сек, n), rows in пул.map(стр, работа):
        if not rows:
            continue
        накоп['стр'].append(f'{сек}:{n}')
        готово += 1
        for x in rows:
            if not isinstance(x, dict):
                continue
            имя = (x.get('organizerName') or '').strip()
            if not имя:
                continue
            з = накоп['орг'].setdefault(имя, {'n': 0, 'ids': [], 'сек': []})
            з['n'] += 1
            if len(з['ids']) < 6:
                з['ids'].append(f"{x.get('sectionAlias') or сек}/{x.get('id')}")
            if сек not in з['сек']:
                з['сек'].append(сек)
        if готово % 40 == 0:
            with open(ФАЙЛ, 'w', encoding='utf-8') as f:
                json.dump(накоп, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            print(f'.. страниц {готово}, организаторов {len(накоп["орг"])}', flush=True)
with open(ФАЙЛ, 'w', encoding='utf-8') as f:
    json.dump(накоп, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('ИТОГ ' + json.dumps({'страниц_за_прогон': готово,
                            'страниц_всего': len(накоп['стр']),
                            'организаторов': len(накоп['орг']),
                            'секунд': round(time.time() - НАЧАЛО, 1)},
                           ensure_ascii=False), flush=True)
os._exit(0)
