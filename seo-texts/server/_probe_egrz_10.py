# -*- coding: utf-8 -*-
"""Проба 10: полный КОСФН (разделы), полный список наборов OData, пагинация groupby,
словари ExpertiseDocumentType/ResultType/WorkType.
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


def get(path, timeout=120):
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
LINES = []

# 1. наборы OData
c, b = get('')
sets = []
try:
    sets = [v['name'] for v in json.loads(b.decode('utf-8')).get('value', [])]
except Exception:  # noqa: BLE001
    sets = [b[:300].decode('utf-8', 'replace')]

# 2. полный корень КОСФН
c2, b2 = get('Kosfn')
kos = []
try:
    for v in (json.loads(b2.decode('utf-8')).get('Values') or []):
        kos.append((v.get('Path', '')[:8], v.get('Text') or v.get('Name') or ''))
except Exception as e:  # noqa: BLE001
    kos = [('err', str(e))]

# 3. groupby с пагинацией
rows, skip = [], 0
while True:
    q = ("PublicRegistrationBook?$apply=filter(ExpertiseConclusionDate gt %s)"
         "/groupby((FunctionalPurpose),aggregate($count as C))&$top=200&$skip=%d" % (FROM, skip))
    c3, b3 = get(q)
    try:
        v = json.loads(b3.decode('utf-8')).get('value') or []
    except Exception:  # noqa: BLE001
        LINES.append('groupby err code=%s %s' % (c3, b3[:200].decode('utf-8', 'replace')))
        break
    rows.extend((str(r.get('FunctionalPurpose') or ''), r.get('C') or 0) for r in v)
    LINES.append('groupby страница skip=%d -> %d строк (code=%s)' % (skip, len(v), c3))
    if len(v) < 200 or skip > 1400:
        break
    skip += 200

# 4. словари прочих полей
DICTS = {}
for f in ('ExpertiseDocumentType', 'ExpertiseResultType', 'WorkType', 'ExpertiseType'):
    c4, b4 = get("PublicRegistrationBook?$apply=filter(ExpertiseConclusionDate gt %s)"
                 "/groupby((%s),aggregate($count as C))&$top=60" % (FROM, f))
    try:
        DICTS[f] = [(str(r.get(f) or '(пусто)'), r.get('C') or 0)
                    for r in (json.loads(b4.decode('utf-8')).get('value') or [])]
        DICTS[f].sort(key=lambda x: -x[1])
    except Exception as e:  # noqa: BLE001
        DICTS[f] = [('err %s %s' % (e, b4[:150].decode('utf-8', 'replace')), 0)]

by_sec = defaultdict(int)
for name, cnt in rows:
    by_sec[(name.split(' ', 1)[0] or '??')[:2]] += cnt

KW = ('производ', 'промышл', 'цех', 'завод', 'склад', 'элеватор', 'нефт', 'газ',
      'металл', 'пищев', 'агро', 'хранилищ', 'котельн', 'компрессор', 'энергет',
      'перерабат', 'фабрик', 'комбинат', 'логист', 'горнодоб', 'химич', 'машиностро',
      'убойн', 'молоч', 'мясо', 'зерно', 'теплич', 'животновод', 'птицевод')
ind = [(n, c_) for n, c_ in rows if any(k in n.lower() for k in KW)]
ind.sort(key=lambda x: x[1])

print('OData наборы:', sets)
for l in LINES:
    print(l)
print('всего групп FunctionalPurpose: %d, сумма: %d' % (len(rows), sum(c for _, c in rows)))
print()
print('--- КОСФН корень (%d) ---' % len(kos))
for p, t in kos:
    print('   %-10s %s' % (p, str(t)[:90]))
print()
for f, vals in DICTS.items():
    print('--- %s ---' % f)
    for n, c_ in vals[:14]:
        print('   %6d  %s' % (c_, n[:100]))
print()
print('--- разделы КОСФН в реестре за 90 дней (по возрастанию) ---')
for k in sorted(by_sec, key=lambda x: by_sec[x]):
    print('   %-4s %d' % (k, by_sec[k]))
print()
print('==== ПРОМЫШЛЕННЫЕ КОДЫ за 90 дней (важное внизу) ====')
for n, c_ in ind:
    print('%6d  %s' % (c_, n[:120]))
print('ИТОГО: %d записей в %d кодах' % (sum(c for _, c in ind), len(ind)))
