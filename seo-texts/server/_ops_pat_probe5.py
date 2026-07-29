# -*- coding: utf-8 -*-
"""Разведка №5: e-disclosure за антиботом ServicePipe — чем его брать, и чем заменить.

A) e-disclosure через браузер (Playwright) и через дельфина.
B) АЛЬТЕРНАТИВНЫЕ уполномоченные агентства раскрытия — их пять, вдруг открыты.
C) Годовые отчёты PDF прямо из выдачи (сайт эмитента).
"""
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402

print('### A. e-disclosure через браузер')
try:
    import browser_probe as BP
    u = ('https://www.e-disclosure.ru/poisk-po-kompaniyam?queryString='
         + urllib.parse.quote('Криогенмаш'))
    out = BP.probe({'url': u, 'solve': True, 'return_html': True,
                    'html_cap': 200000, 'wait_ms': 9000, 'screenshot': False})
    h = out.get('html', '') or ''
    t = EC._текст(h)
    print('  playwright: html', len(h), 'текст', len(t), 'капча',
          out.get('captcha_type'), 'ошибка', str(out.get('error'))[:80])
    print('   ТЕКСТ[0:500]:', repr(t[:500]))
    for m in list(re.finditer(r'href="([^"]*(?:company|files)\.aspx[^"]*)"', h, re.I))[:8]:
        print('   CO:', m.group(1)[:110])
except Exception as ex:  # noqa: BLE001
    print('  playwright ИСКЛ', type(ex).__name__, str(ex)[:120])

print('### B. другие агентства раскрытия')
альт = [
    'https://disclosure.skrin.ru/',
    'https://disclosure.1prime.ru/',
    'https://www.e-disclosure.azipi.ru/',
    'https://disclosure.interfax.ru/',
    'https://www.list-org.com/',
]
for u in альт:
    try:
        h, m, meta = EC._fetch_site(u)
    except Exception as ex:  # noqa: BLE001
        print(' ', u[:45], 'ИСКЛ', type(ex).__name__, str(ex)[:60])
        continue
    t = EC._текст(h or '')
    print(' ', u[:45], '| режим', m, '| html', len(h or ''), '| текст', len(t),
          '|', repr(t[:110]))

print('### C. годовые отчёты PDF из выдачи')
for имя in ('Калужский турбинный завод', 'Уралхиммаш', 'Криогенмаш'):
    for з in (f'{имя} годовой отчёт совет директоров правление pdf',
              f'{имя} список аффилированных лиц'):
        u = EC._serp_urls(з, 8)
        print('  ЗАПРОС:', з[:60], '->', len(u))
        for x in u:
            print('     ', x[:115])
        time.sleep(0.3)
print('ПРОБА5 ЗАВЕРШЕНА')
