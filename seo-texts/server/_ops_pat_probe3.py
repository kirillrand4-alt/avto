# -*- coding: utf-8 -*-
"""Разведка №3: точный разбор патента (авторы+патентообладатель) и вход в e-disclosure."""
import json
import re
import sys
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402


def дай(u):
    try:
        h, m, meta = EC._fetch_site(u)
    except Exception as ex:  # noqa: BLE001
        return '', f'ИСКЛ {type(ex).__name__}: {str(ex)[:60]}'
    return (h or ''), f'режим={m} html={len(h or "")} капча={(meta or {}).get("captcha_type")}'


print('### A. ПОЛНЫЙ JSON одного результата XHR')
u = ('https://patents.google.com/xhr/query?url='
     + urllib.parse.quote('q=' + '"Калужский турбинный завод"', safe='') + '&exp=')
h, инфо = дай(u)
print(' ', инфо)
try:
    j = json.loads(h)
    рез = j['results']['cluster'][0]['result']
    print('  КЛЮЧИ result[0]:', list(рез[0].keys()))
    print('  КЛЮЧИ patent:', list((рез[0].get('patent') or {}).keys()))
    print('  ЦЕЛИКОМ patent[0]:', json.dumps(рез[0]['patent'], ensure_ascii=False)[:1200])
except Exception as ex:  # noqa: BLE001
    print('  сбой', type(ex).__name__, repr(h[:200]))

print('### B. СТРАНИЦА ПАТЕНТА — авторы и патентообладатель')
for pn in ('RU2237170C2', 'RU2399466C1'):
    h, инфо = дай(f'https://patents.google.com/patent/{pn}/ru')
    t = EC._текст(h)
    print(' ', pn, инфо, 'текст', len(t))
    m = re.search(r'Inventor\s+(.{0,700}?)\s+(?:Original|Current)\s+Assignee', t, re.S)
    print('   INVENTOR-БЛОК:', repr((m.group(1) if m else '')[:400]))
    m2 = re.search(r'(?:Original|Current)\s+Assignee\s+(.{0,300}?)\s+Priority date', t, re.S)
    print('   ASSIGNEE-БЛОК:', repr((m2.group(1) if m2 else '')[:300]))

print('### C. findpatent.ru/search.pl')
for u in ('https://findpatent.ru/search.pl?q=' + urllib.parse.quote('Калужский турбинный завод'),
          'https://findpatent.ru/search.pl?text=' + urllib.parse.quote('Калужский турбинный завод')):
    h, инфо = дай(u)
    t = EC._текст(h)
    print(' ', u[:80], '|', инфо, '| текст', len(t))
    print('   ТЕКСТ[0:350]:', repr(t[:350]))
    for m in list(re.finditer(r'href="(/patent/[^"]+)"', h))[:5]:
        print('   PAT:', m.group(1))

print('### D. e-disclosure.ru — поиск компании')
for u in ('https://www.e-disclosure.ru/poisk-po-kompaniyam?queryString=' +
          urllib.parse.quote('Калужский турбинный завод'),
          'https://www.e-disclosure.ru/poisk-po-kompaniyam?query=' +
          urllib.parse.quote('Криогенмаш')):
    h, инфо = дай(u)
    t = EC._текст(h)
    print(' ', u[:95], '|', инфо, '| текст', len(t))
    print('   ТЕКСТ[0:400]:', repr(t[:400]))
    for m in list(re.finditer(r'href="([^"]*(?:company|files)\.aspx[^"]*)"', h, re.I))[:6]:
        print('   CO:', m.group(1)[:100])
print('ПРОБА3 ЗАВЕРШЕНА')
