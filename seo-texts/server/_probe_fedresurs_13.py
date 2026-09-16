# -*- coding: utf-8 -*-
"""Проба 13: карта допустимых Limit, карточка залога/гарантии, тест темпа 120 запросов."""
import io, sys, json, ssl, time
import urllib.request, urllib.error, urllib.parse
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


print('=== A. карта Limit 1..20 + круглые ===')
row = []
for lim in list(range(1, 21)) + [25, 45, 49, 50, 55]:
    c, _ = get(B + 'companies?SearchString=6665002150&Limit=%d&Offset=0' % lim)
    row.append('%d:%s' % (lim, 'ok' if c == 200 else c))
    time.sleep(0.15)
print('  ' + ' '.join(row))

print('\n=== B. семантика SearchString (без падений) ===')
for s in ('Производство насосов', 'компрессор', 'ОЗНА'):
    c, d = jj(B + 'companies?SearchString=%s&Limit=5&Offset=0' % urllib.parse.quote(s))
    rows = (d or {}).get('pageData') or []
    nm = (rows[0].get('name') or '') if rows else ''
    ok = (rows[0].get('okvedName') or '') if rows else ''
    print('  %-24s code=%s found=%-7s %s | %s' % (s, c, (d or {}).get('found'), nm[:30], ok[:30]))
    time.sleep(0.3)

print('\n=== C. карточки: залог / гарантия / увеличение УК / концессия ===')
INNS2 = ('7722607816 3443013396 4701000013 4715030610 5250043567 6164288981 6404001667 '
         '6629022962 6671156423 7017005289 1658087524 2124009521 2308065678 2315014748 '
         '3015087458 3127000014 4223030694 5036074848 6685066917 7414003633').split()
WANT = ['CreationRightOfPledge2', 'IssueIndependentGuarantee',
        'FirmAuthorizedCapitalIncrease', 'ConclusionConcessionAgreement', 'FirmCreated']
done = {}
for inn in INNS2:
    if len(done) == len(WANT):
        break
    c, d = jj(B + 'companies?SearchString=%s&Limit=5&Offset=0' % inn)
    hit = [r for r in ((d or {}).get('pageData') or []) if r.get('inn') == inn]
    if not hit:
        continue
    g = hit[0]['guid']
    ref = 'https://fedresurs.ru/company/' + g
    for t in WANT:
        if t in done:
            continue
        c, d2 = jj(B + 'companies/%s/publications?OnlySfact=true&Type=%s&Limit=5&Offset=0' % (g, t), ref)
        rows = (d2 or {}).get('pageData') or []
        if rows:
            mg = rows[0]['guid']
            c3, b3 = get(B + 'sfact-messages/' + mg, 'https://fedresurs.ru/sfactmessages/' + mg)
            try:
                dd = json.loads(b3.decode('utf-8', 'replace'))
                done[t] = (inn, sorted((dd.get('content') or {}).keys()),
                           json.dumps(dd.get('content'), ensure_ascii=False)[:800])
            except Exception:
                pass
        time.sleep(0.15)
for t in WANT:
    if t in done:
        inn, keys, js = done[t]
        print('  --- %s (ИНН %s)\n      ключи: %s\n      %s' % (t, inn, keys, js))
    else:
        print('  --- %s: в выборке 20 ИНН нет' % t)

print('\n=== D. ТЕМП: 120 запросов, пауза 0.3с ===')
codes, t0 = [], time.time()
for i in range(120):
    c, _ = get(B + 'companies?SearchString=%s&Limit=5&Offset=0' % INNS2[i % len(INNS2)])
    codes.append(c)
    time.sleep(0.3)
print('  за %.0fс: %s' % (time.time() - t0, dict(Counter(codes))))
print('  %s' % ''.join('.' if x == 200 else ('x' if x == 429 else ('!' if x else '?')) for x in codes))
print('\n==== КОНЕЦ ПРОБЫ 13 ====')
