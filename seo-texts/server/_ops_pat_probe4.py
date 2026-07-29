# -*- coding: utf-8 -*-
"""Разведка №4: сырьё там, где предыдущий проход дал ноль.

Ноль мог быть дефектом разбора, поэтому смотрим БАЙТЫ:
 A) e-disclosure: html есть (1756 б), текст 0 — что там буквально?
 B) Google Patents отдал «Sorry...» (лимит) — пробуем прокси VC._fetch и дельфина.
 C) findpatent.ru: POST-форма поиска.
"""
import json
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402
import verify_company as VC      # noqa: E402

print('### A. e-disclosure сырьё')
for u in ('https://www.e-disclosure.ru/poisk-po-kompaniyam?queryString=' +
          urllib.parse.quote('Криогенмаш'),
          'https://www.e-disclosure.ru/',
          'https://www.e-disclosure.ru/portal/company.aspx?id=1234'):
    try:
        req = urllib.request.Request(u, headers={
            'User-Agent': VC.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
            'Accept': 'text/html,application/xhtml+xml'})
        with EC._DIRECT.open(req, timeout=30) as r:
            raw = r.read()
            ct = r.headers.get('Content-Type', '')
            код = r.getcode()
            хед = dict(r.headers)
    except Exception as ex:  # noqa: BLE001
        print(' ', u[:70], 'ИСКЛ', type(ex).__name__, str(ex)[:80])
        continue
    txt = EC._раскодировать(raw, ct)
    print(' ', u[:75], '| код', код, '| ct', ct, '| байт', len(raw),
          '| символов', len(txt))
    print('   БАЙТЫ[0:400]:', repr(raw[:400]))
    print('   РАСКОДИРОВАНО[0:400]:', repr(txt[:400]))
    print('   Location:', хед.get('Location'), '| Refresh:', хед.get('Refresh'))

print('### B. Google Patents через прокси/дельфина')
u = ('https://patents.google.com/xhr/query?url='
     + urllib.parse.quote('q="Уралхиммаш"', safe='') + '&exp=')
try:
    h, m, meta = VC._fetch(u)
    print('  VC._fetch: режим', m, 'len', len(h or ''), 'капча',
          (meta or {}).get('captcha_type'), '| нач:', repr((h or '')[:150]))
except Exception as ex:  # noqa: BLE001
    print('  VC._fetch ИСКЛ', type(ex).__name__, str(ex)[:80])
# прямой, но с паузой и другим UA
import time
time.sleep(5)
try:
    req = urllib.request.Request(u, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                      ' (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Accept': 'application/json,text/plain,*/*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'Referer': 'https://patents.google.com/'})
    with EC._DIRECT.open(req, timeout=30) as r:
        b = r.read()
    print('  прямой+UA: len', len(b), '| нач:', repr(b[:200]))
except Exception as ex:  # noqa: BLE001
    print('  прямой+UA ИСКЛ', type(ex).__name__, str(ex)[:100])

print('### C. findpatent POST')
try:
    данные = urllib.parse.urlencode({'q': 'Калужский турбинный завод',
                                     'text': 'Калужский турбинный завод'}).encode()
    req = urllib.request.Request('https://findpatent.ru/search.pl', data=данные,
                                 headers={'User-Agent': VC.UA,
                                          'Content-Type':
                                          'application/x-www-form-urlencoded'})
    with EC._DIRECT.open(req, timeout=30) as r:
        raw = r.read()
        ct = r.headers.get('Content-Type', '')
    t = EC._раскодировать(raw, ct)
    print('  POST len', len(raw), '| текст', len(EC._текст(t)))
    print('  ССЫЛКИ:', [m.group(1) for m in
                        list(re.finditer(r'href="(/patent/[^"]+)"', t))[:6]])
    print('  ТЕКСТ[0:400]:', repr(EC._текст(t)[:400]))
except Exception as ex:  # noqa: BLE001
    print('  POST ИСКЛ', type(ex).__name__, str(ex)[:100])
print('ПРОБА4 ЗАВЕРШЕНА')
