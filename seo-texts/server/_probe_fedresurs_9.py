# -*- coding: utf-8 -*-
"""Проба 9: боевой путь по ИНН — companies?SearchString=ИНН -> guid ->
publications(OnlySfact/DateStart/Type) -> sfact-messages/{guid}. Плюс пределы Limit/Offset
и мягкая проверка рейт-лимита."""
import io, sys, json, ssl, time
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')
B = 'https://fedresurs.ru/backend/'
LOG = []


def get(u, ref='https://fedresurs.ru/'):
    try:
        r = OP.open(urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': '*/*',
                                                       'Referer': ref}), timeout=30)
        c, b = r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        try:
            c, b = e.code, e.read()
        except Exception:
            c, b = e.code, b''
    except Exception as e:
        c, b = 0, repr(e)[:110].encode()
    LOG.append(c)
    return c, b


def jj(u, ref='https://fedresurs.ru/'):
    c, b = get(u, ref)
    try:
        return c, json.loads(b.decode('utf-8', 'replace'))
    except Exception:
        return c, None


INNS = ['6665002150', '0265004219', '3229000246', '1650032058']
DATE_FROM = '2024-09-16'
DATE_TO = '2026-09-16'
found_msg_guid = None

print('=== A. ПОИСК КОМПАНИИ ПО ИНН: /companies?SearchString=<ИНН> ===')
guids = {}
for inn in INNS:
    c, d = jj(B + 'companies?SearchString=%s&Limit=5&Offset=0' % inn,
              ref='https://fedresurs.ru/search/entity?searchString=' + inn)
    rows = (d or {}).get('pageData') or []
    hit = [r for r in rows if r.get('inn') == inn]
    if hit:
        guids[inn] = hit[0]['guid']
    print('  ИНН %s code=%s найдено=%s точное=%s  %s' %
          (inn, c, (d or {}).get('found'), len(hit), (hit[0]['name'][:44] if hit else '')))
    time.sleep(0.4)

print('\n=== B. ГРУППЫ ПУБЛИКАЦИЙ КОМПАНИИ + ЛЕНТА СООБЩЕНИЙ ===')
for inn, g in guids.items():
    ref = 'https://fedresurs.ru/company/' + g
    c, d = jj(B + 'companies/%s/publication-type-groups' % g, ref)
    print('  ИНН %s groups code=%s -> %s' % (inn, c, json.dumps(d, ensure_ascii=False)[:420]))
    c, d = jj(B + 'companies/%s/publications?OnlySfact=true&DateStart=%s&DateEnd=%s&Limit=20&Offset=0'
              % (g, DATE_FROM, DATE_TO), ref)
    rows = (d or {}).get('pageData') or []
    print('    publications code=%s found=%s got=%s' % (c, (d or {}).get('found'), len(rows)))
    if rows:
        print('    поля: %s' % sorted(rows[0].keys()))
        for r in rows[:6]:
            print('      %s | %s | %s | %s' % (r.get('datePublish') or r.get('date'),
                                               r.get('type') or r.get('publicationType'),
                                               (r.get('typeName') or r.get('name') or '')[:60],
                                               r.get('guid')))
        found_msg_guid = found_msg_guid or rows[0].get('guid')
        print('    СЫРОЙ ПЕРВЫЙ: %s' % json.dumps(rows[0], ensure_ascii=False)[:900])
    time.sleep(0.4)

print('\n=== C. ФИЛЬТР ПО ТИПУ (Type=) ===')
if guids:
    inn, g = list(guids.items())[0]
    for t in ('FinancialLeaseContract2', 'CreationRightOfPledge2', 'FirmLicenseGranted',
              'FirmReorganization', 'FirmAuthorizedCapitalIncrease'):
        c, d = jj(B + 'companies/%s/publications?OnlySfact=true&Type=%s&Limit=5&Offset=0' % (g, t),
                  'https://fedresurs.ru/company/' + g)
        print('  Type=%-30s code=%s found=%s' % (t, c, (d or {}).get('found')))
        time.sleep(0.3)

print('\n=== D. КАРТОЧКА СООБЩЕНИЯ /sfact-messages/{guid} ===')
if found_msg_guid:
    c, b = get(B + 'sfact-messages/' + found_msg_guid,
               'https://fedresurs.ru/sfactmessages/' + found_msg_guid)
    print('  code=%s len=%s' % (c, len(b)))
    try:
        d = json.loads(b.decode('utf-8', 'replace'))
        print('  ключи: %s' % sorted(d.keys()))
        print('  json: %s' % json.dumps(d, ensure_ascii=False, indent=1)[:2200])
    except Exception:
        print('  тело: %s' % b[:400].decode('utf-8', 'replace'))
else:
    print('  сообщений не нашлось — карточку не проверить')

print('\n=== E. ПРЕДЕЛЫ Limit / Offset ===')
if guids:
    g = list(guids.values())[0]
    ref = 'https://fedresurs.ru/company/' + g
    for lim in (5, 10, 20, 50, 60, 100):
        c, _ = get(B + 'companies/%s/publications?Limit=%d&Offset=0' % (g, lim), ref)
        print('  publications Limit=%-4s code=%s' % (lim, c))
        time.sleep(0.25)
    for off in (0, 20, 100, 500, 1000, 10000):
        c, _ = get(B + 'companies/%s/publications?Limit=5&Offset=%d' % (g, off), ref)
        print('  publications Offset=%-6s code=%s' % (off, c))
        time.sleep(0.25)
c, _ = get(B + 'companies?SearchString=6665002150&Limit=100&Offset=0')
print('  companies Limit=100 code=%s' % c)
c, _ = get(B + 'companies?SearchString=6665002150&Limit=50&Offset=0')
print('  companies Limit=50  code=%s' % c)

print('\n=== F. ТЕМП: 40 запросов подряд с паузой 0.25с ===')
codes = []
g = list(guids.values())[0] if guids else None
for i in range(40):
    c, _ = get(B + 'companies?SearchString=%s&Limit=5&Offset=0' % INNS[i % len(INNS)])
    codes.append(c)
    time.sleep(0.25)
from collections import Counter
print('  коды: %s' % dict(Counter(codes)))
print('  последовательность: %s' % ''.join('.' if x == 200 else ('!' if x else '?') for x in codes))
print('  ИТОГО по всей пробе: %s' % dict(Counter(LOG)))
print('\n==== КОНЕЦ ПРОБЫ 9 ====')
