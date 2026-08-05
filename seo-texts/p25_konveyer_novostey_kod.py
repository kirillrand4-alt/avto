# -*- coding: utf-8 -*-
"""Что происходит с item МЕЖДУ коллектором и событием. Читаю живой код, а не догадываюсь.

Замер уже разделил «ноль» на три РАЗНЫЕ поломки:

    google   187 сырых → 110 уже виданы → 46 новых → капекс прошёл 1
    zakupki   58 сырых →  47 уже виданы →  3 новых → капекс прошёл 0
    frp        6 сырых →   6 уже виданы →  0 новых
    hh         0 сырых                                (источник реально пуст)

И тут же видно, что чинить надо разное. У zakupki заголовки выглядят так:

    «Электронный аукцион №0371500001226000199»

В таком заголовке НЕТ НИ ОДНОГО значащего слова — ни «компрессор», ни суммы. Если
классификатор смотрит на `title`, zakupki обречён давать ноль ВСЕГДА, сколько ни собирай.
Предмет закупки лежит в другом поле — и вопрос, доезжает ли оно.

У google другое: из 46 новых почти все — Казахстан, водопровод, плоттер, ГОК. Это не
дедуп и не фильтр, это ЗАПРОСЫ приносят не то.

Печатаю исходники: `_news_key`, тело главного цикла, `col_zakupki`, `col_google`, и то,
какие ключи вообще есть у item каждого источника. Ничего не запускает и не пишет.
"""
import inspect
import io
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

print('news_scan.__file__ = %s' % NS.__file__)
ish = io.open(NS.__file__, encoding='utf-8', errors='replace').read().split('\n')
print('строк в файле: %d' % len(ish))


def pokazat(a, b, zagolovok):
    print('\n\n########## %s   строки %d-%d' % (zagolovok, a, b))
    for i in range(max(0, a - 1), min(len(ish), b)):
        print('%5d| %s' % (i + 1, ish[i][:170]))


def istochnik(imya):
    f = getattr(NS, imya, None)
    if f is None:
        print('\n\n########## %s — НЕТ ТАКОГО' % imya)
        return
    try:
        s = inspect.getsource(f)
    except Exception as e:  # noqa: BLE001
        print('\n\n########## %s — исходник не взялся: %s' % (imya, e))
        return
    print('\n\n########## %s' % imya)
    for l in s.split('\n')[:120]:
        print('   %s' % l[:170])


# 1. ключ дедупа: чем именно новость считается «той же»
pokazat(230, 265, '_news_key — чем меряется «уже видели»')

# 2. главный цикл: где капекс, где seen_add, где зов провайдера
pokazat(1240, 1300, 'главный цикл, окрестности _news_key')
pokazat(1640, 1700, 'главный цикл, окрестности seen_add')

# 3. кто и что кладёт в item
for f in ('col_zakupki', 'col_google', 'col_frp', 'col_hh'):
    istochnik(f)

# 4. что вообще передаётся классификатору
istochnik('extract_event')

# 5. капекс-словарь целиком — он режет 45 из 46 новых у google
print('\n\n########## _CAPEX_KW')
print(getattr(NS._CAPEX_KW, 'pattern', '?')[:3000])

# 6. и какие ключи у item каждого источника, вживую и дёшево
print('\n\n########## КЛЮЧИ item по источникам (по одному вызову, без провайдера)')
for imya, zov in (('zakupki', lambda: NS.col_zakupki(['компрессорная установка'], 14, 3)),
                  ('frp', lambda: NS.col_frp(14, 3))):
    try:
        items = zov() or []
    except Exception as e:  # noqa: BLE001
        print('  %-9s упал: %s' % (imya, str(e)[:120]))
        continue
    print('  %-9s items %d' % (imya, len(items)))
    for it in items[:2]:
        print('     ключи: %s' % sorted(it.keys()))
        for k, v in it.items():
            print('       %-12s %s' % (k, re.sub(r'\s+', ' ', str(v))[:160]))
        print('     ---')

print('\nИТОГ ' + json.dumps({'файл': NS.__file__, 'строк': len(ish)}, ensure_ascii=False))
