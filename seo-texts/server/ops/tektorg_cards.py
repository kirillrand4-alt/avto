# -*- coding: utf-8 -*-
"""ТЭК-Торг: открыть карточки организаторов (ИНН + контакт) + добить формат фильтра.
Durable: C:\\seostat\\drop\\drop-storage\\tek_cards.json + tek_orgs.json."""
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
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
ИСХ = r'C:\seostat\drop\drop-storage\tek_orgs.json'
ВЫХ = r'C:\seostat\drop\drop-storage\tek_cards.json'
БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
НАЧАЛО = time.time()


def get(u, t=30):
    r = urllib.request.Request(u, headers={
        'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'})
    with OP.open(r, timeout=t) as f:
        return EC._раскодировать(f.read(), f.headers.get('Content-Type', ''))


def nd(h):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h or '', re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:  # noqa: BLE001
        return {}


def карточка(путь):
    try:
        d = nd(get(B + путь))
    except Exception:  # noqa: BLE001
        return None
    pp = (d.get('props') or {}).get('pageProps') or {}
    pi = pp.get('procedureItem')
    if not isinstance(pi, dict):
        return None
    пред = str(pi.get('name') or pi.get('title') or '')
    for л in (pi.get('lots') or [])[:5]:
        if isinstance(л, dict):
            пред += ' ' + str(л.get('name') or л.get('lotName') or '')
    return {'путь': путь, 'inn': str(pi.get('inn') or ''), 'kpp': str(pi.get('kpp') or ''),
            'орг': pi.get('organizerName') or '',
            'person': (pi.get('contactPerson') or '').strip(),
            'phone': (pi.get('contactPhone') or '').strip(),
            'email': (pi.get('contactEmail') or '').strip(),
            'дата': ((pi.get('dates') or {}).get('datePublished') or '')[:10],
            'статус': pi.get('statusName') or '',
            'предмет': re.sub(r'\s+', ' ', пред).strip()[:220]}


# ---- 0. формат фильтра: sectionsCodes должен резать выдачу, если формат верный
ТЕСТ = []
for q in ('sectionsCodes[0]=rosneft', 'organizerCodes[0]=6227007322_623401001',
          'organizerCodes[0]=%D0%90%D0%9E%20%22%D0%A0%D0%9D%D0%9F%D0%9A%22',
          'organizerInn[0]=6227007322'):
    try:
        h = get(f'{B}/procedures?{q}')
        d = nd(h)
        lp = (((d.get('props') or {}).get('pageProps') or {})
              .get('initialReduxState') or {}).get('listingProcedures') or {}
        it = lp.get('data') or []
        ТЕСТ.append({'q': q, 'total': lp.get('total'),
                     'секции': sorted({x.get('sectionAlias') for x in it})[:6],
                     'орг': sorted({(x.get('organizerName') or '')[:30] for x in it})[:3]})
    except Exception as ex:  # noqa: BLE001
        ТЕСТ.append({'q': q, 'err': repr(ex)[:70]})
print('ФИЛЬТР ' + json.dumps(ТЕСТ, ensure_ascii=False)[:1600], flush=True)

# ---- 1. карточки организаторов
исх = json.load(open(ИСХ, encoding='utf-8'))
пути = []
for имя, z in исх['орг'].items():
    for сид in (z.get('ids') or [])[:3]:
        сек, _, pid = сид.partition('/')
        if pid:
            пути.append(f'/{сек}/procedures/{pid}')
накоп = {}
if os.path.exists(ВЫХ):
    try:
        накоп = json.load(open(ВЫХ, encoding='utf-8'))
    except Exception:  # noqa: BLE001
        накоп = {}
накоп.setdefault('карточки', {})
пути = [p for p in пути if p not in накоп['карточки']]
print('карточек к открытию ' + str(len(пути)), flush=True)


def раб(p):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return p, None
    return p, карточка(p)


n = 0
with ThreadPoolExecutor(max_workers=8) as пул:
    for p, c in пул.map(раб, пути):
        if c:
            накоп['карточки'][p] = c
            n += 1
        if n and n % 60 == 0:
            with open(ВЫХ, 'w', encoding='utf-8') as f:
                json.dump(накоп, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            print(f'.. карточек {n}', flush=True)
with open(ВЫХ, 'w', encoding='utf-8') as f:
    json.dump(накоп, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
к = list(накоп['карточки'].values())
св = {'карточек': len(к),
      'уник_инн': len({x['inn'] for x in к if x['inn']}),
      'с_контактом': sum(1 for x in к if x['person'] or x['phone'] or x['email']),
      'с_фио': sum(1 for x in к if x['person']),
      'с_почтой': sum(1 for x in к if x['email']),
      'с_телефоном': sum(1 for x in к if x['phone']),
      'секунд': round(time.time() - НАЧАЛО, 1)}
print('ИТОГ ' + json.dumps(св, ensure_ascii=False), flush=True)
print('ФИЛЬТР2 ' + json.dumps(ТЕСТ, ensure_ascii=False)[:1600], flush=True)
os._exit(0)
