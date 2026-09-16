# -*- coding: utf-8 -*-
"""Проба 13: лимиты $top/$skip, счётчики по разделам КОСФН за 90 дней,
доля записей с ИНН застройщика. Коротко, важное — В КОНЦЕ."""
import re
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
FROM = '2026-06-18T00:00:00Z'


def j(path, timeout=120):
    url = API + urllib.parse.quote(path, safe="/?&$=,()'*+:.-_%")
    h = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
         'Origin': 'https://egrz.ru', 'Referer': 'https://egrz.ru/'}
    try:
        r = _OP.open(urllib.request.Request(url, headers=h), timeout=timeout)
        return r.getcode(), json.loads(r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        b = (e.read() if e.fp else b'')
        return e.code, {'_raw': b[:140].decode('utf-8', 'replace')}
    except Exception as e:  # noqa: BLE001
        return -1, {'_raw': 'ERR %s: %s' % (type(e).__name__, e)}


# 1. лимиты $top на обычной выборке и на $apply
TOPS = []
for t in (50, 100, 150, 200, 500, 1000):
    c, d = j("PublicRegistrationBook?$top=%d&$select=Key&$orderby=ExpertiseConclusionDate desc" % t)
    TOPS.append(('plain $top=%d' % t, c, len(d.get('value') or []), str(d.get('_raw', ''))[:60]))
for t in (100, 150, 200):
    c, d = j("PublicRegistrationBook?$apply=filter(ExpertiseConclusionDate gt %s)"
             "/groupby((SubjectRfCode),aggregate($count as C))&$top=%d" % (FROM, t))
    TOPS.append(('apply $top=%d' % t, c, len(d.get('value') or []), str(d.get('_raw', ''))[:60]))
c, d = j("PublicRegistrationBook?$top=5&$skip=100000&$select=Key&$orderby=ExpertiseConclusionDate desc")
TOPS.append(('$skip=100000', c, len(d.get('value') or []), str(d.get('_raw', ''))[:60]))

# 2. счётчики по разделам за 90 дней
SEC = []
for n in range(1, 21):
    p = '%02d.' % n
    c, d = j("PublicRegistrationBook?$count=true&$top=0&$filter=ExpertiseConclusionDate gt %s"
             " and startswith(FunctionalPurpose,'%s')" % (FROM, p))
    SEC.append((p, c, d.get('@odata.count'), str(d.get('_raw', ''))[:50]))
c, d = j("PublicRegistrationBook?$count=true&$top=0&$filter=ExpertiseConclusionDate gt %s" % FROM)
ALL90 = d.get('@odata.count')

# 3. промышленный фильтр-кандидат: разделы 06..11 + 01.01.006 + 01.06.001
IND = ("(startswith(FunctionalPurpose,'06.') or startswith(FunctionalPurpose,'07.')"
       " or startswith(FunctionalPurpose,'08.') or startswith(FunctionalPurpose,'09.')"
       " or startswith(FunctionalPurpose,'10.') or startswith(FunctionalPurpose,'11.')"
       " or startswith(FunctionalPurpose,'01.01.006') or startswith(FunctionalPurpose,'01.06.001'))")
c, d = j("PublicRegistrationBook?$count=true&$top=0&$filter=ExpertiseConclusionDate gt %s and %s"
         % (FROM, IND))
IND_CNT, IND_CODE = d.get('@odata.count'), c

# 4. доля ИНН на выборке 150 записей
c2, d2 = j("PublicRegistrationBook?$top=150&$orderby=ExpertiseConclusionDate desc"
           "&$filter=ExpertiseConclusionDate gt %s and %s" % (FROM, IND))
vals = d2.get('value') or []
inn_re = re.compile(r'ИНН:\s*(\d{10,12})')
with_inn = sum(1 for v in vals if inn_re.search(
    (v.get('DeveloperOrganizationInfo') or '') + (v.get('TechnicalCustomerOrganizationInfo') or '')
    + (v.get('DeveloperAndTechnicalCustomerOrganizationInfo') or '')))
SAMPLES = []
for v in vals[:8]:
    blob = ((v.get('DeveloperOrganizationInfo') or '')
            or (v.get('DeveloperAndTechnicalCustomerOrganizationInfo') or '')
            or (v.get('TechnicalCustomerOrganizationInfo') or ''))
    m = inn_re.search(blob)
    nm = re.match(r'\s*([^(]{3,90})', blob)
    SAMPLES.append((v.get('ExpertiseConclusionDate', '')[:10], (v.get('FunctionalPurpose') or '')[:34],
                    (nm.group(1).strip() if nm else '')[:46], m.group(1) if m else '-',
                    (v.get('ExpertiseObjectName') or '')[:70]))

print('--- лимиты ---')
for n, c_, ln, raw in TOPS:
    print('   %-16s code=%-5s строк=%-5d %s' % (n, c_, ln, raw))
print()
print('--- записей по разделам КОСФН за 90 дней (всего за 90 дней: %s) ---' % ALL90)
for p, c_, cnt, raw in SEC:
    print('   %-5s code=%-5s count=%-8s %s' % (p, c_, cnt, raw))
print()
print('==== ПРОМФИЛЬТР (06-11 + 01.01.006 + 01.06.001) ====')
print('code=%s, записей за 90 дней: %s' % (IND_CODE, IND_CNT))
print('на выборке %d: с ИНН застройщика/техзаказчика = %d (%.0f%%)'
      % (len(vals), with_inn, 100.0 * with_inn / max(1, len(vals))))
print('--- примеры ---')
for dt, fp, nm, inn, obj in SAMPLES:
    print('%s | %-34s | ИНН %-12s | %-46s | %s' % (dt, fp, inn, nm, obj))
