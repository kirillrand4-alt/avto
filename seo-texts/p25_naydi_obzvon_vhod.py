# -*- coding: utf-8 -*-
"""Найти приложение app.obzvon и его вход: форму login-box, роут и установку куки.

Обзвон — отдельное приложение. Форма centro (login-box, поля username/password) постит
не на /obzvon/centro (там 405). Значит вход обрабатывает middleware или отдельный роут
этого приложения, и он ставит сессионную куку. Прибор ищет по всему seostat файлы, где
встречается login-box или обработка входа обзвона, и печатает строки про форму, POST,
куку и сверку пароля. Значений не печатает.
"""
import collections
import io
import json
import os
import re

KORNI = (r'C:\seostat\app', r'C:\seostat')
CEL = re.compile(r'login-box|login_box|set_cookie|Set-Cookie|response\.set_cookie|'
                 r'max_age|obzvon.*(?:auth|login)|OBZVON_USERS|check.*passw|'
                 r'RedirectResponse|303|Response\(|@app\.(?:post|get)|@router\.(?:post|get)|'
                 r'add_middleware|middleware\(', re.I)
seen = set()
nashli = collections.defaultdict(list)
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if re.search(r'[\\/](?:node_modules|\.git|__pycache__|\.venv|dist)[\\/]',
                     put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith(('.py', '.html', '.jinja', '.j2')):
                continue
            p = os.path.join(put, f)
            if p in seen:
                continue
            seen.add(p)
            try:
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if 'obzvon' not in t.lower() and 'login-box' not in t and 'login_box' not in t:
                continue
            for i, s in enumerate(t.split('\n')):
                if CEL.search(s):
                    nashli[p].append((i + 1, s.strip()[:130]))

# Печатаем файлы, где вход обзвона наиболее вероятен (есть login-box или set_cookie).
poryadok = sorted(nashli, key=lambda p: -sum(
    1 for _, s in nashli[p] if re.search(r'login-box|cookie|passw|post|redirect', s, re.I)))
for p in poryadok[:12]:
    sil = [x for x in nashli[p]
           if re.search(r'login-box|cookie|passw|post|redirect|middleware|OBZVON_USERS',
                        x[1], re.I)]
    if not sil:
        continue
    print('\n=== %s' % p)
    for n, s in sil[:16]:
        print('  %-5d %s' % (n, s))

print('ИТОГ ' + json.dumps({'файлов с обзвоном': len(nashli)}, ensure_ascii=False))
