# -*- coding: utf-8 -*-
"""Проба 8: словарь FunctionalPurpose (КОСФН) по свежим записям, сервис-документ OData,
поиск поля со сметной стоимостью.
Только чтение и печать. Главное — ПОСЛЕДНИМ."""
import ssl
import json
import urllib.request
import urllib.error
import urllib.parse

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
API = 'https://open-api.egrz.ru/api/'


def get(path, timeout=90):
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


REP = []

# 1. сервис-документ: какие ещё наборы есть
c, b = get('')
REP.append(('service-doc', c, b[:600].decode('utf-8', 'replace')))

# 2. поле со сметой? спросим несуществующее поле — сервер обычно перечисляет допустимые
for f in ('EstimatedCost', 'SmetaCost', 'Cost'):
    c2, b2 = get("PublicRegistrationBook?$top=1&$select=" + f)
    REP.append(('select ' + f, c2, b2[:300].decode('utf-8', 'replace')))

# 3. словари
for p in ('dictionary/getTepValues', 'organizations?$top=1'):
    c3, b3 = get(p)
    REP.append((p, c3, b3[:300].decode('utf-8', 'replace')))

# 4. распределение FunctionalPurpose по свежим записям (последние ~90 дней)
GROUP = []
c4, b4 = get("PublicRegistrationBook?$apply=filter(ExpertiseConclusionDate gt "
             "2026-06-18T00:00:00Z)/groupby((FunctionalPurpose),aggregate($count as C))")
try:
    d = json.loads(b4.decode('utf-8'))
    rows = d.get('value') or []
    rows.sort(key=lambda r: -(r.get('C') or 0))
    GROUP = [(r.get('FunctionalPurpose'), r.get('C')) for r in rows]
except Exception as e:  # noqa: BLE001
    GROUP = [('parse err %s / %s' % (e, b4[:200].decode('utf-8', 'replace')), 0)]

print()
print('==================== ИТОГ ====================')
for n, c_, head in REP:
    print('--- %s (code=%s) ---' % (n, c_))
    print('   ', head.replace('\n', ' ')[:420])
print()
print('--- FunctionalPurpose за 90 дней: %d значений, код=%s ---' % (len(GROUP), c4))
for name, cnt in GROUP[:120]:
    print('%6s  %s' % (cnt, str(name)[:110]))
