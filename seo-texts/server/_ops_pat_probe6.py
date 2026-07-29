# -*- coding: utf-8 -*-
"""Разведка №6: финальная притирка обоих разборов перед замером.

A) Патенты: XHR через VC._fetch (прокси) — полный словарь патента; страница
   патента — полный список авторов; сверка патентообладателя.
B) Раскрытие: читается ли PDF отчёта эмитента, что такое .uif у 1prime,
   и есть ли PDF на странице раскрытия эмитента.
"""
import json
import re
import sys
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402
import verify_company as VC      # noqa: E402


def гет(u):
    try:
        h, m, meta = VC._fetch(u)
        return (h or ''), f'{m} len={len(h or "")} капча={(meta or {}).get("captcha_type")}'
    except Exception as ex:  # noqa: BLE001
        return '', f'ИСКЛ {type(ex).__name__}: {str(ex)[:60]}'


print('### A1. XHR полный словарь патента')
u = ('https://patents.google.com/xhr/query?url='
     + urllib.parse.quote('q="Калужский турбинный завод"', safe='') + '&exp=')
h, инфо = гет(u)
print(' ', инфо)
try:
    j = json.loads(h)
    рез = j['results']['cluster'][0]['result']
    print('  всего:', j['results'].get('total_num_results'), 'на стр:', len(рез))
    print('  ЦЕЛИКОМ patent[0]:', json.dumps(рез[0]['patent'], ensure_ascii=False)[:900])
    print('  assignee/inventor по всем:')
    for r in рез[:10]:
        p = r['patent']
        print('    ', p.get('publication_number'), '| A:', str(p.get('assignee'))[:55],
              '| I:', str(p.get('inventor'))[:70])
except Exception as ex:  # noqa: BLE001
    print('  сбой', type(ex).__name__, repr(h[:200]))

print('### A2. страница патента — все авторы')
h, инфо = гет('https://patents.google.com/patent/RU2237170C2/ru')
t = EC._текст(h)
print(' ', инфо, 'текст', len(t))
m = re.search(r'\bInventor\b(.{0,900}?)(?:Original|Current)\s+Assignee', t, re.S)
print('  INVENTOR:', repr((m.group(1) if m else '')[:500]))
m2 = re.search(r'(?:Original|Current)\s+Assignee(.{0,400}?)(?:Priority date|Application|Publication)', t, re.S)
print('  ASSIGNEE:', repr((m2.group(1) if m2 else '')[:300]))

print('### B1. PDF отчёта эмитента')
for u in ('https://uralhimmash.ru/upload/aktsioneram/'
          '%D0%9E%D1%82%D1%87%D0%B5%D1%82_%D0%BE%D0%B1_%D0%B8%D1%82%D0%BE%D0%B3'
          '%D0%B0%D1%85_%D0%B3%D0%BE%D0%BB%D0%BE%D1%81%D0%BE%D0%B2%D0%B0%D0%BD'
          '%D0%B8%D1%8F_30.06.2026_%D0%93%D0%97%D0%9E%D0%A1%D0%90_.pdf',
          'https://cryogenmash.ru/upload/iblock/d0f/'
          'd0fbcc9b8a2b68cd39865484eeb5f2cd.pdf'):
    try:
        t = EC.doc_text(u)
    except Exception as ex:  # noqa: BLE001
        print(' ', u[:60], 'ИСКЛ', type(ex).__name__, str(ex)[:60])
        continue
    print(' ', u[-45:], '| символов', len(t))
    print('   ТЕКСТ[0:600]:', repr(t[:600]))
    for кл in ('нженер', 'иректор', 'равлени', 'овет директоров'):
        for mm in list(re.finditer(кл, t))[:2]:
            print('    [%s] …%s…' % (кл, t[max(0, mm.start()-140):
                                          mm.start()+160].replace('\n', ' ')))

print('### B2. .uif у 1prime')
u = 'https://disclosure.1prime.ru/news/-12/{8CEA7C72-754E-4DBF-A4D4-3661E84B9EB0}.uif'
h, инфо = гет(u)
print(' ', инфо)
t = EC._текст(h)
print('   ТЕКСТ[0:500]:', repr(t[:500]))

print('### B3. страница раскрытия эмитента -> PDF')
h, инфо = гет('https://paoktz.ru/invest/reports/')
print(' ', инфо)
for m in list(re.finditer(r'href="([^"]+\.pdf)"', h, re.I))[:10]:
    print('   PDF:', urllib.parse.unquote(m.group(1))[:110])
print('ПРОБА6 ЗАВЕРШЕНА')
