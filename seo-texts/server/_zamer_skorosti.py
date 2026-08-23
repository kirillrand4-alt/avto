# -*- coding: utf-8 -*-
r"""Замер: сколько секунд на компанию у сбора после правок."""
import importlib
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
LS = importlib.import_module('lid_ssylka')
importlib.reload(LS)
КЕШ = r'C:\seostat\drop\pagecache'
файлы = sorted(os.listdir(КЕШ))[:60]
t0 = time.time()
n = стр = ном = 0
самая_долгая = (0, '')
for имя in файлы:
    if not имя.endswith('.json.gz'):
        continue
    инн = имя.split('.')[0]
    t1 = time.time()
    страницы = LS._stranicy_kesha(инн)
    если = LS._kontakty_so_stranic(страницы)
    д = time.time() - t1
    if д > самая_долгая[0]:
        самая_долгая = (round(д, 2), инн + ' страниц %d' % len(страницы))
    n += 1
    стр += len(страницы)
    ном += len((если or {}).get('tel') or {})
всего = time.time() - t0
print(json.dumps({'компаний': n, 'секунд': round(всего, 1),
                  'на_компанию_сек': round(всего / max(1, n), 2),
                  'страниц_всего': стр, 'номеров': ном,
                  'самая_долгая': самая_долгая}, ensure_ascii=False, indent=1))
