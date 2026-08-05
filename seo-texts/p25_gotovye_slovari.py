# -*- coding: utf-8 -*-
"""ГОТОВЫЕ словари конвейера — читаю их целиком, прежде чем строить своё.

Владелец: «там же был готовый список слов, по которому искались новости, сначала
разберись как работают инструменты, а потом придумывай своё». Он прав, и это ровно та
ошибка, за которую я сама ругаю приборы: я собрала свой список «нашей машины» из чтения
сигналов, не посмотрев тот, что уже зашит в конвейер и по которому новости и искались.

Печатаю ЦЕЛИКОМ, без сокращений и без своих комментариев поверх:

    TRIGGERS            что считается поводом (формы запроса к поиску)
    KC_INDUSTRIES       отрасли направления «компрессоры»
    MEYER_INDUSTRIES    отрасли направления «фотосепараторы/рентген»
    HH_SIGNALS          вакансии-сигналы расширения
    _hh_equipment       вакансия -> какое оборудование за ней стоит
    _CAPEX_KW           капекс-предфильтр
    _VK_TRASH           минус-словарь ВК
    VK-запросы          готовые q-строки к newsfeed.search
    каталог лент        региональные ленты
    OKVED_DIRECTIONS    77 кодов владельца: кто наш клиент по роду занятий

Печатает по одному словарю на строку с длиной, а сами списки — в конце, самым длинным
последним: хвост раннера хранит конец вывода.
"""
import inspect
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

print('news_scan.__file__ = %s' % NS.__file__)

IMENA = ['TRIGGERS', 'KC_INDUSTRIES', 'MEYER_INDUSTRIES', 'HH_SIGNALS',
         'ZAKUPKI_KW', 'ZAKUPKI_KEYWORDS', 'VK_QUERIES', 'VK_Q', 'FEEDS',
         '_CAPEX_KW', '_VK_TRASH', '_VK_DIGEST', 'FULLTEXT_CAP', '_VK_SLEEP']

print('\n=== ЧТО ВООБЩЕ ЕСТЬ В МОДУЛЕ (списки и словари верхнего уровня)')
for n in sorted(dir(NS)):
    if n.startswith('__'):
        continue
    v = getattr(NS, n)
    if isinstance(v, (list, tuple, set, dict)):
        print('  %-26s %-8s len=%d' % (n, type(v).__name__, len(v)))
    elif isinstance(v, re.Pattern):
        print('  %-26s regex    %d знаков' % (n, len(v.pattern)))

print('\n=== ОКВЭД-НАПРАВЛЕНИЯ (кто наш клиент по роду занятий)')
try:
    import enrich_db as EDB
    print('enrich_db.__file__ = %s' % EDB.__file__)
    m = getattr(EDB, 'OKVED_DIRECTIONS', None)
    if isinstance(m, dict):
        print('  кодов: %d' % len(m))
        for k in sorted(m):
            print('    %-12s %s' % (k, m[k]))
    else:
        print('  OKVED_DIRECTIONS нет, тип %s' % type(m))
        print('  похожее: %s' % [n for n in dir(EDB)
                                 if 'OKVED' in n.upper() or 'DIRECT' in n.upper()])
except Exception as e:  # noqa: BLE001
    print('  %s: %s' % (type(e).__name__, str(e)[:160]))

print('\n\n=== _hh_equipment: вакансия -> оборудование')
try:
    for l in inspect.getsource(NS._hh_equipment).split('\n')[:60]:
        print('   %s' % l[:160])
except Exception as e:  # noqa: BLE001
    print('   %s' % e)

print('\n\n=== _VK_TRASH (минус-словарь) и _CAPEX_KW')
for n in ('_VK_TRASH', '_CAPEX_KW'):
    v = getattr(NS, n, None)
    if v is not None:
        print('\n  %s:\n%s' % (n, getattr(v, 'pattern', v)))

print('\n\n=== СПИСКИ ЦЕЛИКОМ')
for n in IMENA:
    v = getattr(NS, n, None)
    if v is None or isinstance(v, re.Pattern):
        continue
    if isinstance(v, dict):
        print('\n--- %s (%d)' % (n, len(v)))
        for k in list(v)[:200]:
            print('    %-30s %s' % (str(k)[:30], str(v[k])[:110]))
    elif isinstance(v, (list, tuple, set)):
        print('\n--- %s (%d)' % (n, len(v)))
        for x in list(v)[:300]:
            print('    %s' % str(x)[:150])

# VK-запросы могут строиться функцией, а не лежать списком
print('\n\n=== ОТКУДА БЕРУТСЯ VK-ЗАПРОСЫ')
for n in sorted(dir(NS)):
    if 'vk' in n.lower() and callable(getattr(NS, n, None)) and not n.startswith('col_'):
        try:
            s = inspect.getsource(getattr(NS, n))
            if 'q' in s and ('quer' in s or 'запрос' in s):
                print('\n--- %s' % n)
                for l in s.split('\n')[:40]:
                    print('   %s' % l[:160])
        except Exception:  # noqa: BLE001
            pass

print('\nИТОГ ' + json.dumps({'файл': NS.__file__}, ensure_ascii=False))
