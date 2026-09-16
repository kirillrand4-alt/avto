# -*- coding: utf-8 -*-
"""Проба 9: КОСФН — разделы классификатора, агрегаты по префиксам, промышленные коды,
плюс проверка наличия поля со сметной стоимостью.
Печатаем ПО ВОЗРАСТАНИЮ важности: самое нужное — В КОНЦЕ."""
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


SHORT = []
# смета: пробуем несуществующие поля — ответ покажет, есть ли похожие
for f in ('EstimatedCost', 'SmetaCost', 'Cost', 'TepValues'):
    c, b = get("PublicRegistrationBook?$top=1&$select=" + f)
    SHORT.append(('$select=' + f, c, b[:200].decode('utf-8', 'replace').replace('\n', ' ')))
c, b = get('')
SHORT.append(('service-doc', c, b[:400].decode('utf-8', 'replace').replace('\n', ' ')))
c, b = get('Kosfn')
roots = []
try:
    d = json.loads(b.decode('utf-8'))
    for v in (d.get('Values') or [])[:30]:
        roots.append((v.get('Index'), str(v.get('Text') or v.get('Name') or v)[:90]))
except Exception as e:  # noqa: BLE001
    roots = [(0, 'parse err %s %s' % (e, b[:200].decode('utf-8', 'replace')))]
SHORT.append(('Kosfn', c, str(roots)[:600]))

# распределение за 90 дней
c4, b4 = get("PublicRegistrationBook?$apply=filter(ExpertiseConclusionDate gt "
             "2026-06-18T00:00:00Z)/groupby((FunctionalPurpose),aggregate($count as C))")
rows = []
try:
    rows = [(str(r.get('FunctionalPurpose') or ''), r.get('C') or 0)
            for r in (json.loads(b4.decode('utf-8')).get('value') or [])]
except Exception as e:  # noqa: BLE001
    rows = [('ERR %s %s' % (e, b4[:200].decode('utf-8', 'replace')), 0)]

by_sec = defaultdict(int)
by_grp = defaultdict(int)
grp_name = {}
for name, cnt in rows:
    code = name.split(' ', 1)[0]
    by_sec[code[:2]] += cnt
    by_grp[code[:5]] += cnt
    grp_name.setdefault(code[:5], name)

KW = ('производ', 'промышл', 'цех', 'завод', 'склад', 'элеватор', 'нефт', 'газ',
      'металл', 'пищев', 'агро', 'хранилищ', 'котельн', 'компрессор', 'энергет',
      'перерабат', 'фабрик', 'комбинат', 'логист', 'горнодоб', 'химич', 'машиностро')
ind = [(n, c_) for n, c_ in rows if any(k in n.lower() for k in KW)]
ind.sort(key=lambda x: x[1])

print('--- короткие пробы ---')
for n, c_, head in SHORT:
    print('%-16s code=%-5s %s' % (n, c_, head[:380]))
print()
print('всего различных FunctionalPurpose за 90 дней: %d, сумма записей: %d'
      % (len(rows), sum(c_ for _, c_ in rows)))
print()
print('--- разделы (первые 2 цифры) ---')
for k in sorted(by_sec):
    print('  %s -> %d' % (k, by_sec[k]))
print()
print('--- группы XX.XX (по возрастанию, важное внизу) ---')
for k in sorted(by_grp, key=lambda x: by_grp[x]):
    print('  %-7s %-6d %s' % (k, by_grp[k], grp_name[k][:80]))
print()
print('==== ПРОМЫШЛЕННЫЕ/ПРОИЗВОДСТВЕННЫЕ КОДЫ за 90 дней (по возрастанию) ====')
for n, c_ in ind:
    print('%6d  %s' % (c_, n[:120]))
print('ИТОГО промышленных записей за 90 дней: %d в %d кодах'
      % (sum(c_ for _, c_ in ind), len(ind)))
