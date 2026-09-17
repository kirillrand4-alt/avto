# -*- coding: utf-8 -*-
"""Контроль после правки verify_company: не сломались ли соседи.

Правку зовут четыре модуля, поэтому мало того, что «мой замер прошёл»: надо убедиться, что
файл импортируется начисто, что общий `_BEZ_PROXY` остался прежним (им ходят на ЧУЖИЕ
сайты) и что тяжёлый `enrich_contacts` по-прежнему поднимается.
"""
import os
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
SERV = r'C:\sender\server'

print('### 1. импорт verify_company начисто')
t0 = time.time()
import verify_company as VC  # noqa: E402

print('  импортирован за %.1f с, файл %s' % (time.time() - t0, VC.__file__))
print('  правка на месте: %s' % hasattr(VC, '_soedinit_perebor'))
print('  сигнатура не тронута: _provider_call_stdlib%s'
      % __import__('inspect').signature(VC._provider_call_stdlib))
print('  _BEZ_PROXY на месте и это обычный опенер: %s / %s'
      % (hasattr(VC, '_BEZ_PROXY'), type(getattr(VC, '_BEZ_PROXY', None)).__name__))
print('  отдельный опенер шлюза заведён: %s' % hasattr(VC, '_SHLYUZ_OPENER'))
print('  разные объекты (общий опенер НЕ подменён): %s'
      % (getattr(VC, '_BEZ_PROXY', 1) is not getattr(VC, '_SHLYUZ_OPENER', 2)))

print('\n### 2. кто берёт из verify_company имена напрямую (from ... import)')
for imya in sorted(os.listdir(SERV)):
    if not imya.endswith('.py'):
        continue
    try:
        t = open(os.path.join(SERV, imya), encoding='utf-8', errors='replace').read()
    except Exception:  # noqa: BLE001
        continue
    for i, l in enumerate(t.split('\n'), 1):
        if re.search(r'from\s+verify_company\s+import|VC\._BEZ_PROXY|verify_company\._BEZ_PROXY', l):
            print('  %-24s %5d| %s' % (imya, i, l.strip()[:88]))

print('\n### 3. тяжёлые соседи поднимаются')
for mod in ('news_scan', 'enrich_contacts'):
    t0 = time.time()
    try:
        __import__(mod)
        print('  %-18s импортирован за %.1f с' % (mod, time.time() - t0))
    except Exception as ex:  # noqa: BLE001
        print('  %-18s НЕ ИМПОРТИРУЕТСЯ: %s: %s' % (mod, type(ex).__name__, str(ex)[:140]))

print('\n### 4. живой вызов через штатный путь (3 подряд)')
ok = 0
for i in range(3):
    t0 = time.time()
    try:
        out = VC._provider_call_stdlib('Ответь одним словом: работает')
        ok += 1
        print('  %d: ОТВЕТ %r за %.1f с' % (i + 1, (out or '')[:24], time.time() - t0))
    except Exception as ex:  # noqa: BLE001
        print('  %d: СБОЙ за %.1f с: %s: %s' % (i + 1, time.time() - t0,
                                                type(ex).__name__, str(ex)[:100]))
print('\n=== ИТОГ КОНТРОЛЯ: живых вызовов %d из 3 ===' % ok)
