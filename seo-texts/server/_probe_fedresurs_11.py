# -*- coding: utf-8 -*-
"""Проба 11: пределы Limit, тело 451, per-company обременения, реальная статистика
типов сообщений по 16 промышленным ИНН + карточки нужных типов."""
import io, sys, json, ssl, time
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


INNS = '5042059767 5031003120 9108000588 6665002150 2540021263 0265004219 3229000246 ' \
       '6027024000 1434031363 1001040512 6330017980 5260041350 6658081585 6454002828 ' \
       '0269007362 2457029066'.split()

print('=== A. допустимые Limit ===')
ok, bad = [], []
for lim in [1, 3, 5, 8, 10, 15, 20, 25, 30, 40, 50, 51, 100]:
    c, _ = get(B + 'companies?SearchString=6665002150&Limit=%d&Offset=0' % lim)
    (ok if c == 200 else bad).append(lim if c == 200 else (lim, c))
    time.sleep(0.2)
print('  200: %s' % ok)
print('  НЕ 200: %s' % bad)

print('\n=== B. тело ответа 451 ===')
c, b = get(B + 'companies?SearchString=6665002150&Limit=20&Offset=0')
print('  code=%s len=%s body=%r' % (c, len(b), b[:300].decode('utf-8', 'replace')))

print('\n=== C. per-company обременения /companies/{guid}/encumbrances ===')
c, d = jj(B + 'companies?SearchString=6665002150&Limit=5&Offset=0')
G = (d or {}).get('pageData', [{}])[0].get('guid')
c, b = get(B + 'companies/%s/encumbrances' % G, 'https://fedresurs.ru/company/' + G)
print('  code=%s len=%s %s' % (c, len(b), b[:600].decode('utf-8', 'replace')))

print('\n=== D. статистика типов по 16 промышленным ИНН (publication-type-groups) ===')
types = Counter()
comps = Counter()
guids = {}
for inn in INNS:
    c, d = jj(B + 'companies?SearchString=%s&Limit=5&Offset=0' % inn)
    hit = [r for r in ((d or {}).get('pageData') or []) if r.get('inn') == inn]
    if not hit:
        print('  %s — не найден (code=%s)' % (inn, c))
        continue
    g = hit[0]['guid']
    guids[inn] = g
    c, d = jj(B + 'companies/%s/publication-type-groups' % g, 'https://fedresurs.ru/company/' + g)
    sf = ((d or {}).get('sfacts') or {})
    seen = set()
    for grp in (sf.get('groups') or []) + [{'types': sf.get('withoutGroup') or []}]:
        for t in grp.get('types') or []:
            types[(t.get('code'), (t.get('description') or '')[:44])] += t.get('count') or 0
            seen.add(t.get('code'))
    for cd in seen:
        comps[cd] += 1
    time.sleep(0.25)
print('  компаний обработано: %d' % len(guids))
print('  %-38s %-46s сообщ / компаний' % ('код', 'название'))
for (code, name), n in types.most_common(40):
    print('  %-38s %-46s %5d / %d' % (code, name, n, comps[code]))

print('\n=== E. КАРТОЧКИ КЛЮЧЕВЫХ ТИПОВ (content -> есть ли сумма/предмет) ===')
WANT = ['FinancialLeaseContract2', 'CreationRightOfPledge2', 'FirmLicenseGranted',
        'FirmReorganization', 'FirmAuthorizedCapitalIncrease', 'FirmAssetsValue',
        'IssueIndependentGuarantee', 'ConclusionConcessionAgreement', 'FirmCreated']
done = set()
for t in WANT:
    for inn, g in guids.items():
        if t in done:
            break
        c, d = jj(B + 'companies/%s/publications?OnlySfact=true&Type=%s&Limit=5&Offset=0' % (g, t),
                  'https://fedresurs.ru/company/' + g)
        rows = (d or {}).get('pageData') or []
        if rows:
            mg = rows[0]['guid']
            c2, b2 = get(B + 'sfact-messages/' + mg, 'https://fedresurs.ru/sfactmessages/' + mg)
            try:
                dd = json.loads(b2.decode('utf-8', 'replace'))
                cont = dd.get('content') or {}
                print('  --- %s (ИНН %s, %s) ---' % (t, inn, dd.get('datePublish', '')[:10]))
                print('      ключи content: %s' % sorted(cont.keys()))
                print('      %s' % json.dumps(cont, ensure_ascii=False)[:800])
            except Exception as e:
                print('  --- %s: карточка code=%s %r' % (t, c2, str(e)[:60]))
            done.add(t)
        time.sleep(0.2)
    if t not in done:
        print('  --- %s: в этой выборке нет' % t)
print('\n==== КОНЕЦ ПРОБЫ 11 ====')
