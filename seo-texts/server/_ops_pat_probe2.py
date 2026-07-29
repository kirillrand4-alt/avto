# -*- coding: utf-8 -*-
"""Разведка №2: ищем МАССОВЫЙ вход в патенты, а не по одной ссылке из выдачи.

1) Google Patents XHR-поиск по ПАТЕНТООБЛАДАТЕЛЮ (assignee) — отдаёт JSON.
2) findpatent.ru: где у него настоящий поиск (домашняя страница, форма).
3) patentdb.ru/owner/86030 — сырой HTML: правда ли пусто (текст был 29 символов).
4) freepatent.ru — есть ли свой поиск.
"""
import json
import re
import sys
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402


def сыро(u, n=700):
    try:
        h, m, meta = EC._fetch_site(u)
    except Exception as ex:  # noqa: BLE001
        return None, f'ИСКЛ {type(ex).__name__}: {str(ex)[:70]}'
    return h, f'режим={m} html={len(h or "")} капча={(meta or {}).get("captcha_type")}'


print('### 1. GOOGLE PATENTS XHR по assignee')
for q in ('assignee:"Калужский турбинный завод"',
          'assignee:"Уралхиммаш"',
          '"Калужский турбинный завод"'):
    u = ('https://patents.google.com/xhr/query?url='
         + urllib.parse.quote('q=' + q, safe='') + '&exp=')
    h, инфо = сыро(u)
    print(' Q:', q, '|', инфо)
    if h:
        try:
            j = json.loads(h)
            кл = (j.get('results') or {}).get('cluster') or []
            рез = (кл[0].get('result') if кл else []) or []
            print('   результатов:', len(рез), '| всего по метаданным:',
                  (j.get('results') or {}).get('total_num_results'))
            for r in рез[:4]:
                p = r.get('patent') or {}
                print('    ', p.get('publication_number'), '|',
                      str(p.get('assignee'))[:60], '| inv:',
                      str(p.get('inventor'))[:60], '|',
                      str(p.get('title'))[:50])
        except Exception as ex:  # noqa: BLE001
            print('   НЕ JSON:', type(ex).__name__, '| начало:', repr(h[:250]))

print('### 2. findpatent.ru — форма поиска')
h, инфо = сыро('https://findpatent.ru/')
print(' главная |', инфо)
if h:
    for m in list(re.finditer(r'<form[^>]*>', h, re.I))[:5]:
        print('   FORM:', m.group(0)[:200])
    for m in list(re.finditer(r'href="(/[^"]{0,60}(?:search|poisk|owner|byowner)[^"]*)"',
                              h, re.I))[:8]:
        print('   LINK:', m.group(1)[:90])

print('### 3. patentdb.ru/owner/86030 — сырой HTML')
h, инфо = сыро('https://patentdb.ru/owner/86030')
print(' ', инфо)
print('  HTML[0:900]:', repr((h or '')[:900]))

print('### 4. freepatent.ru поиск')
for u in ('http://www.freepatent.ru/',
          'http://www.freepatent.ru/search?q=' +
          urllib.parse.quote('Калужский турбинный завод')):
    h, инфо = сыро(u)
    print(' ', u[:70], '|', инфо)
    if h and u.endswith('/'):
        for m in list(re.finditer(r'<form[^>]*>', h, re.I))[:4]:
            print('   FORM:', m.group(0)[:200])
print('ПРОБА2 ЗАВЕРШЕНА')
