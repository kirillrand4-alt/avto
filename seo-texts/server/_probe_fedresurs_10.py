# -*- coding: utf-8 -*-
"""Проба 10: что такое 451 (гипотеза — недопустимое значение Limit), затем полноценная
выборка публикаций и карточка сообщения."""
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


INN = '6665002150'
c, d = jj(B + 'companies?SearchString=%s&Limit=5&Offset=0' % INN)
G = (d or {}).get('pageData', [{}])[0].get('guid')
REF = 'https://fedresurs.ru/company/' + str(G)
print('guid %s = %s' % (INN, G))

print('\n=== A. допустимые значения Limit (companies?SearchString=) ===')
ok, bad = [], []
for lim in [1, 2, 3, 5, 8, 10, 15, 20, 25, 30, 40, 50, 51, 75, 100]:
    c, b = get(B + 'companies?SearchString=%s&Limit=%d&Offset=0' % (INN, lim))
    (ok if c == 200 else bad).append((lim, c))
    time.sleep(0.25)
print('  200: %s' % [x[0] for x in ok])
print('  не 200: %s' % bad)

print('\n=== B. тело ответа 451 ===')
c, b = get(B + 'companies?SearchString=%s&Limit=20&Offset=0' % INN)
print('  code=%s len=%s body=%s' % (c, len(b), b[:400].decode('utf-8', 'replace')))

print('\n=== C. повтор ОДНОГО И ТОГО ЖЕ Limit=20 пять раз (детерминизм?) ===')
seq = []
for _ in range(5):
    c, _b = get(B + 'companies?SearchString=%s&Limit=20&Offset=0' % INN)
    seq.append(c)
    time.sleep(0.3)
print('  %s' % seq)
seq = []
for _ in range(5):
    c, _b = get(B + 'companies?SearchString=%s&Limit=15&Offset=0' % INN)
    seq.append(c)
    time.sleep(0.3)
print('  Limit=15: %s' % seq)

print('\n=== D. per-company обременения (robots это НЕ запрещает) ===')
c, b = get(B + 'companies/%s/encumbrances' % G, REF)
print('  code=%s len=%s %s' % (c, len(b), b[:700].decode('utf-8', 'replace')))

print('\n=== E. ПУБЛИКАЦИИ с допустимым Limit ===')
msg_guid = None
for q in ('?OnlySfact=true&Limit=15&Offset=0',
          '?OnlySfact=true&DateStart=2023-01-01&DateEnd=2026-09-16&Limit=15&Offset=0',
          '?OnlySfact=true&Type=FinancialLeaseContract2&Limit=15&Offset=0'):
    c, d = jj(B + 'companies/%s/publications%s' % (G, q), REF)
    rows = (d or {}).get('pageData') or []
    print('  %s -> code=%s found=%s got=%s' % (q, c, (d or {}).get('found'), len(rows)))
    if rows and not msg_guid:
        print('     поля: %s' % sorted(rows[0].keys()))
        for r in rows[:8]:
            print('     %s' % json.dumps(r, ensure_ascii=False)[:260])
        msg_guid = rows[0].get('guid')
    time.sleep(0.4)

print('\n=== F. КАРТОЧКА СООБЩЕНИЯ ===')
if msg_guid:
    c, b = get(B + 'sfact-messages/' + msg_guid, 'https://fedresurs.ru/sfactmessages/' + msg_guid)
    print('  /sfact-messages/%s code=%s len=%s' % (msg_guid, c, len(b)))
    try:
        d = json.loads(b.decode('utf-8', 'replace'))
        print('  ключи: %s' % sorted(d.keys()))
        print(json.dumps(d, ensure_ascii=False, indent=1)[:2600])
    except Exception:
        print('  %s' % b[:500].decode('utf-8', 'replace'))
print('\n==== КОНЕЦ ПРОБЫ 10 ====')
