# -*- coding: utf-8 -*-
"""Разведка №1: КАК устроены страницы патентных баз. Ничего не меряем, смотрим сырьё.

Проверяем на двух заведомо «патентных» заводах:
  - выдаёт ли xmlriver ссылки на findpatent.ru / patentdb.ru / patents.google.com;
  - читается ли страница патента (кодировка!) и что в ней есть буквально;
  - работает ли ПРЯМОЙ поиск по findpatent.ru без выдачи.
Печатаем сырые куски, чтобы «пусто» нельзя было списать на разбор.
"""
import json
import re
import sys
import time
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_contacts as EC     # noqa: E402

ЦЕЛИ = [('Калужский турбинный завод', 'paoktz.ru'),
        ('Уралхиммаш', 'uralhimmash.ru')]

for имя, дом in ЦЕЛИ:
    print('=' * 20, имя)
    ссылки = []
    for з in (f'"{имя}" патент авторы изобретения',
              f'{имя} патентообладатель findpatent',
              f'{имя} патент site:patentdb.ru'):
        u = EC._serp_urls(з, 10)
        print('  ЗАПРОС:', з, '->', len(u))
        for x in u:
            print('     ', x[:120])
        ссылки += u
        time.sleep(0.3)
    # прямой поиск findpatent без выдачи
    for шаблон in ('https://findpatent.ru/search/?q=%s',
                   'https://patentdb.ru/search?q=%s'):
        u = шаблон % urllib.parse.quote(имя)
        try:
            h, m, meta = EC._fetch_site(u)
        except Exception as ex:  # noqa: BLE001
            print('  ПРЯМОЙ', u[:60], 'ИСКЛ', type(ex).__name__, str(ex)[:60])
            continue
        t = EC._текст(h or '')
        print('  ПРЯМОЙ', u[:70], '| режим', m, '| html', len(h or ''),
              '| текст', len(t), '| капча', (meta or {}).get('captcha_type'))
        print('    СЫРОЙ ТЕКСТ[0:400]:', repr(t[:400]))
    # читаем первую страницу патента из выдачи
    прочитано = 0
    for u in ссылки:
        d = EC._domain(u)
        if not any(k in d for k in ('findpatent', 'patentdb', 'patents.google',
                                    'patenton', 'yandex.ru/patents', 'freepatent')):
            continue
        if прочитано >= 2:
            break
        try:
            h, m, meta = EC._fetch_site(u)
        except Exception as ex:  # noqa: BLE001
            print('  СТР', u[:80], 'ИСКЛ', type(ex).__name__)
            continue
        t = EC._текст(h or '')
        прочитано += 1
        print('  СТР', u[:90], '| режим', m, '| текст', len(t))
        for кл in ('Автор', 'атентооблад', 'Заявител', 'Изобретател', 'Assignee',
                   'Inventor'):
            for mm in list(re.finditer(кл, t))[:2]:
                print('     [%s] …%s…' % (кл, t[max(0, mm.start()-60):
                                                mm.start()+320].replace('\n', ' ')))
        if not t:
            print('     ПУСТО, СЫРОЙ HTML[0:300]:', repr((h or '')[:300]))
        time.sleep(0.4)
print('ПРОБА ЗАВЕРШЕНА')
