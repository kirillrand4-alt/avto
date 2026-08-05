# -*- coding: utf-8 -*-
"""Google News отдаёт заглушку, и она уезжает в провайдера целиком. Проверяю и считаю цену.

Замер `fetch_article` показал вот что (живой сервер, живой код):

    google   из 4 items текст достали у 4, длины [20000, 20000, 20000, 20000]
    начало:  «Минэнерго: строительство НПЗ на Сахалине… body,html{height:100%;
              overflow:hidden}body{-webkit-font-smoothing:antialiased;…»

Двадцать тысяч знаков CSS. Ссылка у Google News это не статья, а редирект-заглушка
`news.google.com/rss/articles/CBMi…`; качается заглушка, а в ней — стили и скрипты.

Почему это хуже, чем «пусто». В главном цикле стоит

    ev = extract_event(it.get('full_text') or it['title'], …)

Фолбэк на заголовок срабатывает только если `full_text` ПУСТ. А он не пуст — он полон
мусора. Значит заголовок не спасает: модель получает заголовок плюс двадцать тысяч знаков
таблицы стилей и по ним решает, капекс это или нет. И платим мы за каждый такой знак.

ЧТО СЧИТАЮ:
  1. сколько google-item за прогон и сколько это знаков мусора — цена в квоте;
  2. есть ли предфильтр `_CAPEX_KW` ДО провайдера (если нет — платим за всё подряд);
  3. `fetch_article` целиком — где чинить;
  4. и отдельно: у zakupki текст ДОСТАЁТСЯ (5 629 и 20 000 знаков) — надо посмотреть
     глазами, предмет закупки там или тоже заглушка. Печатаю ПОСЛЕДНИМ, потому что хвост
     раннера хранит конец, и в прошлый раз именно это и потерялось.
"""
import inspect
import io
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

ish = io.open(NS.__file__, encoding='utf-8', errors='replace').read().split('\n')

print('=== ГДЕ ВООБЩЕ ПРИМЕНЯЕТСЯ _CAPEX_KW (есть ли предфильтр до провайдера)')
for i, s in enumerate(ish):
    if '_CAPEX_KW' in s:
        for j in range(max(0, i - 4), min(len(ish), i + 3)):
            print('%5d|%s %s' % (j + 1, '>' if j == i else ' ', ish[j][:150]))
        print('     |')

print('\n\n=== fetch_article')
try:
    for l in inspect.getsource(NS.fetch_article).split('\n')[:90]:
        print('   %s' % l[:160])
except Exception as e:  # noqa: BLE001
    print('   %s' % e)

print('\n\n=== ЦЕНА МУСОРА: сколько знаков заглушки уехало бы за один прогон google')
try:
    inds = list(NS.KC_INDUSTRIES) + list(NS.MEYER_INDUSTRIES)
    q = ['%s %s' % (t, ind) for t in NS.TRIGGERS[:2] for ind in inds][:4]
    g = NS.col_google(q, 14, 4) or []
    musor, vsego = 0, 0
    for it in g[:4]:
        it2 = NS.fetch_article(dict(it))
        ft = str(it2.get('full_text') or '')
        vsego += len(ft)
        # доля таблицы стилей/скриптов в тексте
        if re.search(r'\{[a-z-]+:[^}]+\}', ft[:2000]):
            musor += 1
    print('  проверено %d, из них с CSS в первых 2 000 знаках: %d' % (len(g[:4]), musor))
    print('  средняя длина full_text: %d знаков' % (vsego // max(1, len(g[:4]))))
    print('  за прогон google даёт ~187 items -> ~%d тыс. знаков в провайдера'
          % (187 * (vsego // max(1, len(g[:4]))) // 1000))
except Exception as e:  # noqa: BLE001
    print('  замер упал: %s' % str(e)[:160])

print('\n\n########## ZAKUPKI: что реально в full_text — предмет закупки или заглушка')
try:
    z = NS.col_zakupki(['компрессорная установка', 'генератор азота'], 14, 3) or []
    for it in z[:3]:
        it2 = NS.fetch_article(dict(it))
        ft = re.sub(r'\s+', ' ', str(it2.get('full_text') or ''))
        print('\n  · %s' % str(it.get('title') or '')[:96])
        print('    %s' % str(it.get('link') or '')[:118])
        print('    full_text %d знаков' % len(ft))
        print('    НАЗВАН ЛИ ПРЕДМЕТ: %s'
              % ('ДА' if re.search(r'компрессор|азот|кислород|осушител', ft, re.I) else 'нет'))
        print('    первые 1200 знаков:')
        print('      %s' % ft[:1200])
except Exception as e:  # noqa: BLE001
    print('  упало: %s' % str(e)[:160])

print('\nИТОГ ' + json.dumps({'файл': NS.__file__}, ensure_ascii=False))
