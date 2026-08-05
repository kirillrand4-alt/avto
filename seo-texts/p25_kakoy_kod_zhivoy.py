# -*- coding: utf-8 -*-
"""Какой код ЖИВОЙ: сверить моё предложение с тем, что реально стоит на сервере.

2-я сессия говорит: я смотрела файл из ветки с докой, а живая версия другая — там уже
есть `_canon_role` и шкала на 16 ролей. Если так, мой замер Р-001 мерил правило,
которого в проде нет, и предложение надо снимать или переписывать.

Это моё же правило: большое число — повод проверить прибор. Проверяю ДО того, как
настаивать на внедрении.

Прибор ищет на сервере все файлы, где определяется выбор адресата, и печатает по
каждому: путь, время правки, есть ли `_canon_role`, `_ROLE_CANON`, `_ROLE_RANK`,
`_best_by_role`, сколько ролей в шкале. Ничего не меняет.
"""
import collections
import io
import json
import os
import re

KORNI = (r'C:\sender\server', r'C:\sender', r'C:\sender\_ops')
INTERES = ('_canon_role', '_ROLE_CANON', '_ROLE_RANK', '_best_by_role',
           'best_for_outreach', 'best_email')

nashli = []
seen = set()
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if re.search(r'[\\/](?:node_modules|\.git|__pycache__|_bak)', put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith('.py'):
                continue
            p = os.path.join(put, f)
            if p in seen:
                continue
            seen.add(p)
            try:
                if os.path.getsize(p) > 8 * 1024 * 1024:
                    continue
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if not any(k in t for k in INTERES):
                continue
            est = {k: t.count(k) for k in INTERES if k in t}
            # Сколько ролей в шкале: считаем строки вида ('...',) -> 'роль'
            n_kanon = len(re.findall(r"\)\s*,\s*'([^']+)'\s*\)", t))
            nashli.append({'put': p, 'mtime': int(os.path.getmtime(p)),
                           'kb': os.path.getsize(p) // 1024, 'est': est,
                           'pravil_kanona': n_kanon})

nashli.sort(key=lambda z: -z['mtime'])
print('=== файлы, где решается выбор адресата (свежие сверху)')
for z in nashli[:14]:
    print('\n%s  %d КБ' % (z['put'], z['kb']))
    print('   правлен: %s' % __import__('time').strftime(
        '%m-%d %H:%M', __import__('time').localtime(z['mtime'])))
    print('   %s' % ', '.join('%s×%d' % (k, v) for k, v in z['est'].items()))
    if z['pravil_kanona']:
        print('   правил канона ролей: ~%d' % z['pravil_kanona'])

# Кто из них реально ЗАПИСЫВАЕТ companies.best_email
print('\n=== кто ПИШЕТ companies.best_email (UPDATE/INSERT)')
for z in nashli:
    try:
        t = io.open(z['put'], encoding='utf-8', errors='replace').read()
    except Exception:  # noqa: BLE001
        continue
    for m in re.finditer(r'[^\n]{0,90}(?:UPDATE|update)\s+companies[^\n]{0,110}', t):
        s = re.sub(r'\s+', ' ', m.group(0))
        if 'best_email' in s:
            n = t[:m.start()].count('\n') + 1
            print('  %s:%-5d %s' % (os.path.basename(z['put']), n, s[:120]))

print('ИТОГ ' + json.dumps({'файлов найдено': len(nashli),
                            'самый свежий': nashli[0]['put'] if nashli else ''},
                           ensure_ascii=False))
