# -*- coding: utf-8 -*-
"""Разведка №7: только патенты — XHR через прокси и полный список авторов со страницы."""
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
        return (h or ''), f'{m} len={len(h or "")}'
    except Exception as ex:  # noqa: BLE001
        return '', f'ИСКЛ {type(ex).__name__}: {str(ex)[:60]}'


строки = []
u = ('https://patents.google.com/xhr/query?url='
     + urllib.parse.quote('q="Калужский турбинный завод"', safe='') + '&exp=')
h, инфо = гет(u)
строки.append('XHR ' + инфо)
try:
    j = json.loads(h)
    рез = j['results']['cluster'][0]['result']
    строки.append('всего=%s настр=%d' % (j['results'].get('total_num_results'), len(рез)))
    строки.append('КЛЮЧИ: ' + ','.join((рез[0].get('patent') or {}).keys()))
    for r in рез[:8]:
        p = r['patent']
        строки.append('  %s | A=%s | I=%s' % (p.get('publication_number'),
                                              str(p.get('assignee'))[:50],
                                              str(p.get('inventor'))[:60]))
except Exception as ex:  # noqa: BLE001
    строки.append('сбой %s %r' % (type(ex).__name__, h[:150]))

for pn in ('RU2237170C2', 'RU2399466C1'):
    h, инфо = гет(f'https://patents.google.com/patent/{pn}/ru')
    t = EC._текст(h)
    строки.append('%s %s текст=%d' % (pn, инфо, len(t)))
    m = re.search(r'\bInventor\b(.{0,900}?)(?:Original|Current)\s+Assignee', t, re.S)
    строки.append('  INV: %r' % ((m.group(1) if m else '')[:420],))
    m2 = re.search(r'(?:Original|Current)\s+Assignee(.{0,300}?)'
                   r'(?:Priority date|Application|Publication)', t, re.S)
    строки.append('  ASG: %r' % ((m2.group(1) if m2 else '')[:220],))
    if not t:
        строки.append('  ПУСТО html[0:200]: %r' % (h[:200],))

# 1prime .uif через ПРАВИЛЬНЫЙ краул (с _раскодировать)
u = 'https://disclosure.1prime.ru/news/-12/{8CEA7C72-754E-4DBF-A4D4-3661E84B9EB0}.uif'
try:
    h2, m2_, _ = EC._fetch_site(u)
    t2 = EC._текст(h2 or '')
    строки.append('UIF через _fetch_site: %s текст=%d :: %r' % (m2_, len(t2), t2[:300]))
except Exception as ex:  # noqa: BLE001
    строки.append('UIF ИСКЛ %s' % type(ex).__name__)

print('\n'.join(строки))
print('ПРОБА7 ЗАВЕРШЕНА')
