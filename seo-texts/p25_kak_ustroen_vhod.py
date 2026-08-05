# -*- coding: utf-8 -*-
"""Как устроен вход в панель: middleware basic-auth и СТРУКТУРА токен-файла.

Вход оказался не POST-формой, а HTTP Basic. `_login` читает заголовок Authorization,
«сам заголовок уже проверен middleware'ом». Значит ходить надо с заголовком
`Authorization: Basic base64(имя:пароль)`, а не слать форму — оттого и были 422, потом
429 (перебор имён упёрся в ограничение частоты).

Прибор находит middleware и печатает, как он сверяет логин и пароль и откуда их берёт
(переменная окружения, файл). И отдельно — СТРУКТУРУ токен-файла: длину, есть ли «=» или
«:», префикс из пары символов. Само значение не печатается: секрет остаётся секретом,
а формат виден и без него.
"""
import base64
import io
import json
import os
import re

MW = (r'C:\seostat\app\main.py', r'C:\seostat\app\middleware.py',
      r'C:\seostat\app\api\routes_obzvon.py', r'C:\sender\enrich_panel\enrich_panel.py')
TOKEN_FAYLY = (r'C:\sender\_ops\p25_user3_token.txt',
               r'C:\sender\_ops\p25_user1_token.txt', r'C:\sender\p25_user3_token.txt')

print('=== где и как проверяется basic-auth')
for p in MW:
    if not os.path.exists(p):
        continue
    t = io.open(p, encoding='utf-8', errors='replace').read()
    ls = t.split('\n')
    for i, s in enumerate(ls):
        if re.search(r'basic|authorization|OBZVON_|getenv|environ|401|WWW-Authenticate|'
                     r'compare_digest|password|USERS', s, re.I):
            print('  %s:%-4d %s' % (os.path.basename(p), i + 1, s.strip()[:130]))

print('\n=== СТРУКТУРА токен-файла (значение не печатается)')
for p in TOKEN_FAYLY:
    if not os.path.exists(p):
        print('  нет: %s' % p)
        continue
    syroy = io.open(p, encoding='utf-8', errors='replace').read()
    pervaya = syroy.split('\n')[0]
    opis = {'путь': os.path.basename(p), 'длина': len(syroy.strip()),
            'строк': syroy.count('\n') + 1,
            'есть =': '=' in pervaya, 'есть :': ':' in pervaya,
            'префикс2': pervaya[:2] if pervaya else '',
            'похоже на base64': bool(re.fullmatch(r'[A-Za-z0-9+/=_\-]+', pervaya or ''))}
    # Если это base64(имя:пароль) — покажем ТОЛЬКО имя (до двоеточия), не пароль.
    try:
        dek = base64.b64decode(pervaya + '==').decode('utf-8', 'replace')
        if ':' in dek and dek.count(':') == 1 and dek.isprintable():
            opis['раскодировалось в имя:пароль, имя'] = dek.split(':')[0]
    except Exception:  # noqa: BLE001
        pass
    print('  ' + json.dumps(opis, ensure_ascii=False))

print('ИТОГ ' + json.dumps({'проверено файлов входа': sum(os.path.exists(p) for p in MW)},
                           ensure_ascii=False))
