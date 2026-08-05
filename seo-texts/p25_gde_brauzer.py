# -*- coding: utf-8 -*-
"""Найти на сервере браузерный прибор и вход в панель. Читает, не трогает.

Владелец показал чужой экран, где сказано: прибор умеет `fill_seq`, `click`,
`screenshot` с выкладкой снимка на дроп. Значит браузер на сервере есть, и ходить по
панели глазами можно оттуда. Прежде чем ходить — надо знать, чем и куда.

Прибор ищет три вещи и печатает найденное:
  * файлы, объявляющие операции браузера (клик, ввод, снимок);
  * адрес самой панели (порт, маршрут) — куда идти;
  * как панель пускает: логин, куки, basic-auth, или пускает с localhost без спроса.

Ничего не пишет и никуда не ходит.
"""
import collections
import io
import json
import os
import re

KORNI = (r'C:\sender\server', r'C:\sender', r'C:\seostat')
MOYO = re.compile(r'[\\/](?:_bak[^\\/]*)[\\/]', re.I)
RASSH = ('.py', '.js', '.json', '.ini', '.cfg', '.toml', '.bat', '.ps1')

BRAUZER = re.compile(r'playwright|selenium|puppeteer|chromium|fill_seq|'
                     r'page\.goto|browser\.new_page|screenshot', re.I)
VHOD = re.compile(r'uvicorn|--port|listen|127\.0\.0\.1:|localhost:|0\.0\.0\.0:', re.I)
PUSK = re.compile(r'HTTPBasic|basic_auth|check_credentials|session_cookie|'
                  r'PANEL_USER|PANEL_PASS|BASIC_USER|login_required|Depends\(auth', re.I)

sch = collections.Counter()
nashli = collections.defaultdict(list)
seen = set()
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if re.search(r'[\\/](?:node_modules|\.git|__pycache__|dist)[\\/]', put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith(RASSH):
                continue
            p = os.path.join(put, f)
            if MOYO.search(p) or p in seen:
                continue
            seen.add(p)
            try:
                if os.path.getsize(p) > 3 * 1024 * 1024:
                    continue
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            sch['файлов просмотрено'] += 1
            for rg, imya in ((BRAUZER, 'браузер'), (VHOD, 'адрес панели'),
                             (PUSK, 'как пускает')):
                m = rg.search(t)
                if not m:
                    continue
                n = t[:m.start()].count('\n') + 1
                if len(nashli[imya]) < 22:
                    nashli[imya].append((p[-62:], n, t.split('\n')[n - 1].strip()[:120]))
                sch[imya] += 1

for imya in ('браузер', 'адрес панели', 'как пускает'):
    print('\n=== %s — файлов %d' % (imya, sch[imya]))
    for p, n, s in nashli[imya]:
        print('  %s:%-5d %s' % (p, n, s))
    if not nashli[imya]:
        print('  НЕ НАЙДЕНО')

print('ИТОГ ' + json.dumps({k: sch[k] for k in ('браузер', 'адрес панели', 'как пускает')},
                           ensure_ascii=False))
