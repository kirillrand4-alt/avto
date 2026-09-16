# -*- coding: utf-8 -*-
"""Проба 7: схема PublicRegistrationBook ($metadata), полный набор полей записи,
проверка фильтров (дата + слово в названии объекта + сортировка).
Только чтение и печать. Главное — ПОСЛЕДНИМ."""
import re
import ssl
import json
import urllib.request
import urllib.error

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                  urllib.request.HTTPSHandler(context=_CTX))
API = 'https://open-api.egrz.ru/api/'


def get(url, timeout=60):
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

# 1. метаданные OData
c, b = get(API + '$metadata')
meta = b.decode('utf-8', 'replace')
props = re.findall(r'<Property Name="([^"]+)" Type="([^"]+)"', meta)
ent = re.findall(r'<EntityType Name="([^"]+)"', meta)
REP.append(('$metadata', c, len(b)))

# 2. одна запись — все ключи
c2, b2 = get(API + 'PublicRegistrationBook?$top=1')
keys = []
try:
    d = json.loads(b2.decode('utf-8'))
    keys = sorted((d.get('value') or [{}])[0].keys())
except Exception as e:  # noqa: BLE001
    keys = ['parse err %s' % e]
REP.append(('top1', c2, len(b2)))

# 3. фильтры
TESTS = {
    'date_desc': ("PublicRegistrationBook?$count=true&$top=1"
                  "&$orderby=ExpertiseConclusionDate desc"),
    'date_gt': ("PublicRegistrationBook?$count=true&$top=1&$filter="
                "ExpertiseConclusionDate gt 2026-06-01T00:00:00Z"),
    'zavod': ("PublicRegistrationBook?$count=true&$top=1&$filter="
              "contains(tolower(ExpertiseObjectName),tolower('%D0%B7%D0%B0%D0%B2%D0%BE%D0%B4'))"),
    'zavod_new': ("PublicRegistrationBook?$count=true&$top=1&$orderby=ExpertiseConclusionDate desc"
                  "&$filter=ExpertiseConclusionDate gt 2026-06-18T00:00:00Z and "
                  "contains(tolower(ExpertiseObjectName),tolower('%D1%86%D0%B5%D1%85'))"),
    'pos_only': ("PublicRegistrationBook?$count=true&$top=1&$filter="
                 "ExpertiseResultType eq 'Положительное заключение'"),
}
TEST_OUT = []
SAMPLE = ''
for name, q in TESTS.items():
    cc, bbb = get(API + q.replace(' ', '%20'))
    cnt = ''
    try:
        dd = json.loads(bbb.decode('utf-8'))
        cnt = dd.get('@odata.count')
        if name == 'zavod_new' and dd.get('value'):
            SAMPLE = json.dumps(dd['value'][0], ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass
    TEST_OUT.append((name, cc, cnt, bbb[:180].decode('utf-8', 'replace').replace('\n', ' ')))

print()
print('==================== ИТОГ ====================')
for n, c_, l_ in REP:
    print('%-14s code=%s len=%d' % (n, c_, l_))
print('EntityTypes:', ent[:12])
print('--- Property из $metadata (%d) ---' % len(props))
for n, t in props[:70]:
    print('   %-42s %s' % (n, t))
print('--- ключи записи (%d) ---' % len(keys))
print('   ', ', '.join(keys))
print('--- тесты фильтров ---')
for n, c_, cnt, head in TEST_OUT:
    print('%-10s code=%-5s count=%-10s %s' % (n, c_, cnt, head[:150]))
print('--- ОБРАЗЕЦ записи (цех, свежие) ---')
print(SAMPLE[:2200] if SAMPLE else '(нет)')
