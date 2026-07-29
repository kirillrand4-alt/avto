# -*- coding: utf-8 -*-
"""Разведка №8: русские патентные базы через выдачу — структура страниц.

Google Patents закрылся («Sorry...» и на прямом, и на прокси), поэтому меряем
через findpatent.ru / freepatent.ru: их страницы читаются, а поля «Автор(ы)» и
«Патентообладатель(и)» на них написаны прямым текстом.
"""
import os
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402

ПОТОК = r'C:\sender\_ops\pat_patents.jsonl'
if os.path.exists(ПОТОК):
    os.remove(ПОТОК)
    print('поток очищен')

ЦЕЛИ = ['Калужский турбинный завод', 'Уралхиммаш', 'Соликамский магниевый завод']
ссылки = {}
for имя in ЦЕЛИ:
    соб = []
    for з in (f'"{имя}" патент авторы изобретения findpatent',
              f'"{имя}" патентообладатель изобретение freepatent',
              f'{имя} патенты компании'):
        u = EC._serp_urls(з, 10)
        for x in u:
            d = EC._domain(x)
            if any(k in d for k in ('findpatent', 'freepatent', 'patenton',
                                    'edrid', 'bd.patent')):
                if x not in соб:
                    соб.append(x)
        time.sleep(0.3)
    ссылки[имя] = соб
    print('%-32s -> %d патентных ссылок' % (имя[:32], len(соб)))
    for x in соб[:8]:
        print('     ', x[:110])

print('### СТРУКТУРА СТРАНИЦ')
показано = 0
for имя, соб in ссылки.items():
    for u in соб[:3]:
        if показано >= 5:
            break
        try:
            h, m, meta = EC._fetch_site(u)
        except Exception as ex:  # noqa: BLE001
            print(' ', u[:80], 'ИСКЛ', type(ex).__name__)
            continue
        t = EC._текст(h or '')
        показано += 1
        print(' ', u[:95], '| режим', m, '| текст', len(t))
        if not t:
            print('    ПУСТО, html[0:250]:', repr((h or '')[:250]))
            continue
        for кл in ('Автор', 'атентооблад', 'Заявител'):
            mm = re.search(кл, t)
            if mm:
                print('    [%s] %r' % (кл, t[mm.start():mm.start() + 300]))
        time.sleep(0.4)
print('ПРОБА8 ЗАВЕРШЕНА')
