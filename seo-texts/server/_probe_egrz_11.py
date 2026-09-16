# -*- coding: utf-8 -*-
"""Проба 11: ПОЛНЫЙ словарь FunctionalPurpose ($top=1000) + полный корень КОСФН.
Самое важное — В КОНЦЕ."""
import ssl
import json
import urllib.request
import urllib.error
import urllib.parse
from collections import defaultdict

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
API = 'https://open-api.egrz.ru/api/'


def get(path, timeout=150):
    url = API + urllib.parse.quote(path, safe="/?&$=,()'*+:.-_%")
    h = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
         'Origin': 'https://egrz.ru', 'Referer': 'https://egrz.ru/'}
    try:
        r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, (e.read() if e.fp else b'')
    except Exception as e:  # noqa: BLE001
        return -1, ('ERR %s: %s' % (type(e).__name__, e)).encode()


FROM = '2026-06-18T00:00:00Z'

c2, b2 = get('Kosfn')
kos = []
try:
    kos = [(v.get('Text') or v.get('Name') or '') for v in
           (json.loads(b2.decode('utf-8')).get('Values') or [])]
except Exception as e:  # noqa: BLE001
    kos = ['err %s' % e]

c3, b3 = get("PublicRegistrationBook?$apply=filter(ExpertiseConclusionDate gt %s)"
             "/groupby((FunctionalPurpose),aggregate($count as C))&$top=1000" % FROM)
rows = []
try:
    rows = [(str(r.get('FunctionalPurpose') or '(пусто)'), r.get('C') or 0)
            for r in (json.loads(b3.decode('utf-8')).get('value') or [])]
except Exception as e:  # noqa: BLE001
    rows = [('ERR %s %s' % (e, b3[:200].decode('utf-8', 'replace')), 0)]

by_sec = defaultdict(int)
sec_names = defaultdict(set)
for name, cnt in rows:
    code = name.split(' ', 1)[0]
    s = code[:2] if code[:2].isdigit() else '??'
    by_sec[s] += cnt
    if len(sec_names[s]) < 3:
        sec_names[s].add(name[:70])

# коды разделов 05+ (отраслевые) и промышленные вкрапления раздела 01
NOT_INDUSTRY_01 = True
sel = [(n, c) for n, c in rows
       if (n[:2].isdigit() and int(n[:2]) >= 5)
       or n.startswith('01.01.006') or n.startswith('01.06.001')]
sel.sort(key=lambda x: x[1])

print('код Kosfn=%s, код groupby=%s, групп: %d, сумма: %d'
      % (c2, c3, len(rows), sum(c for _, c in rows)))
print()
print('--- КОСФН корень (%d разделов) ---' % len(kos))
for t in kos:
    print('   ', str(t)[:100])
print()
print('--- разделы в реестре за 90 дней ---')
for k in sorted(by_sec):
    print('   %-4s %-7d %s' % (k, by_sec[k], ' | '.join(sorted(sec_names[k]))[:110]))
print()
print('==== КОДЫ ОТРАСЛЕВЫХ РАЗДЕЛОВ (05+) + промплощадки/склады (важное внизу) ====')
for n, c in sel:
    print('%6d  %s' % (c, n[:120]))
print('ИТОГО по этой выборке: %d записей в %d кодах' % (sum(c for _, c in sel), len(sel)))
