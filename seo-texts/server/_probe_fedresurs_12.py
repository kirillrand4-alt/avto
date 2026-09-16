# -*- coding: utf-8 -*-
"""Проба 12: пределы Limit, тело 451, per-company обременения, справочник регионов,
семантика SearchString, карточка залога, тест темпа (120 запросов)."""
import io, sys, json, ssl, time, urllib.parse
import urllib.request, urllib.error
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                 urllib.request.HTTPSHandler(context=CTX))
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')
B = 'https://fedresurs.ru/backend/'


def get(u, ref='https://fedresurs.ru/'):
    try:
        r = OP.open(urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': '*/*',
                                                       'Referer': ref}), timeout=30)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b''
    except Exception as e:
        return 0, repr(e)[:110].encode()


def jj(u, ref='https://fedresurs.ru/'):
    c, b = get(u, ref)
    try:
        return c, json.loads(b.decode('utf-8', 'replace'))
    except Exception:
        return c, None


print('=== A..D пропущены (уже сняты) ===')
if 0:
  print('=== A. Limit: что принимает ===')
  res = []
  for lim in [1, 3, 5, 8, 10, 15, 20, 25, 30, 40, 50, 51, 100]:
    c, _ = get(B + 'companies?SearchString=6665002150&Limit=%d&Offset=0' % lim)
    res.append('%d:%d' % (lim, c))
    time.sleep(0.2)
print('  ' + '  '.join(res))

print('\n=== B. тело 451 ===')
c, b = get(B + 'companies?SearchString=6665002150&Limit=20&Offset=0')
print('  code=%s len=%s body=%r' % (c, len(b), b[:280].decode('utf-8', 'replace')))
print('  повтор Limit=20: %s %s %s' % tuple(
    get(B + 'companies?SearchString=6665002150&Limit=20&Offset=0')[0] for _ in range(3)))

print('\n=== C. per-company обременения ===')
c, d = jj(B + 'companies?SearchString=6665002150&Limit=5&Offset=0')
G = (d or {}).get('pageData', [{}])[0].get('guid')
c, b = get(B + 'companies/%s/encumbrances' % G, 'https://fedresurs.ru/company/' + G)
print('  code=%s len=%s %s' % (c, len(b), b[:500].decode('utf-8', 'replace')))

print('\n=== D. справочник регионов ===')
c, d = jj(B + 'reference-book/regions')
print('  code=%s тип=%s всего=%s' % (c, type(d).__name__, len(d) if isinstance(d, list) else ''))
if isinstance(d, list):
    print('  первые: %s' % json.dumps(d[:6], ensure_ascii=False))

print('\n=== E. семантика SearchString ===')
for s in ('6665002150', '1026600930707', 'КУМЗ', '28.13', 'Производство насосов'):
    c, d = jj(B + 'companies?SearchString=%s&Limit=5&Offset=0' % urllib.parse.quote(s))
    rows = (d or {}).get('pageData') or []
    print('  %-24s code=%s found=%-6s первый=%s | %s' %
          (s, c, (d or {}).get('found'), ((rows[0].get('name') or '') if rows else '')[:34],
           ((rows[0].get('okvedName') or '') if rows else '')[:36]))
    time.sleep(0.3)

print('\n=== F. поиск карточки залога CreationRightOfPledge2 ===')
INNS2 = '7722607816 3443013396 4701000013 4715030610 5250043567 6164288981 6404001667 ' \
        '6629022962 6671156423 7017005289 1658087524 2124009521 2308065678 2315014748 ' \
        '3015087458 3127000014 4223030694 5036074848 6685066917 7414003633'.split()
card = None
for inn in INNS2:
    c, d = jj(B + 'companies?SearchString=%s&Limit=5&Offset=0' % inn)
    hit = [r for r in ((d or {}).get('pageData') or []) if r.get('inn') == inn]
    if not hit:
        continue
    g = hit[0]['guid']
    for t in ('CreationRightOfPledge2', 'IssueIndependentGuarantee', 'FirmAuthorizedCapitalIncrease'):
        c, d2 = jj(B + 'companies/%s/publications?OnlySfact=true&Type=%s&Limit=5&Offset=0' % (g, t),
                   'https://fedresurs.ru/company/' + g)
        rows = (d2 or {}).get('pageData') or []
        if rows:
            mg = rows[0]['guid']
            c3, b3 = get(B + 'sfact-messages/' + mg, 'https://fedresurs.ru/sfactmessages/' + mg)
            try:
                dd = json.loads(b3.decode('utf-8', 'replace'))
                print('  --- %s (ИНН %s) content-ключи: %s' % (t, inn, sorted((dd.get('content') or {}).keys())))
                print('      %s' % json.dumps(dd.get('content'), ensure_ascii=False)[:1100])
                card = t
            except Exception:
                pass
        time.sleep(0.15)
    if card:
        break
if not card:
    print('  в выборке 20 ИНН таких сообщений нет')

print('\n=== G. ТЕМП: 120 запросов подряд, пауза 0.3с ===')
codes = []
t0 = time.time()
for i in range(120):
    c, _ = get(B + 'companies?SearchString=%s&Limit=5&Offset=0' % INNS2[i % len(INNS2)])
    codes.append(c)
    time.sleep(0.3)
print('  за %.0fс: %s' % (time.time() - t0, dict(Counter(codes))))
print('  последовательность: %s' % ''.join('.' if x == 200 else ('x' if x == 429 else
                                                                 ('!' if x else '?')) for x in codes))
print('\n==== КОНЕЦ ПРОБЫ 12 ====')
