# -*- coding: utf-8 -*-
"""Почему четыре коллектора дали НОЛЬ. Считаю сырые items по каждому, без провайдера.

Прогон news_scan дал 653 сырых, 100 капекс-событий, 62 с ИНН. Но по коллекторам:

    xmlriver-google  64
    xmlriver-yandex  28
    vk                6
    regional          2
    google  0 | zakupki  0 | hh  0 | frp  0     <- четыре из семи молчат

Владелец просил по 10 с КАЖДОГО источника, значит «ноль» надо не констатировать, а
объяснить. Пусто может значить три разных вещи, и это РАЗНЫЕ починки:
  * коллектор не вернул ни одного item — источник закрыт, сломан или блокирует;
  * items были, но их съел дедуп `seen_news` (значит новость уже брали раньше);
  * items были, но провайдер сказал «не капекс» — тогда вопрос к фильтру, не к источнику.

Прибор зовёт каждый коллектор НАПРЯМУЮ теми же дефолтами, что и `collect_all`, и
печатает: сколько сырых, сколько уникальных, и три заголовка для глаз. Провайдера не
трогает — значит ни квоты, ни `seen_news` не расходует.
"""
import collections
import json
import os
import sys
import traceback

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

DAYS = 14
MAX = 10

# Дефолты берутся ИЗ collect_all, а не придумываются: иначе я померю не то, что
# работает в бою.
ZAKUPKI_KW = ['компрессорная установка', 'компрессор винтовой', 'генератор азота',
              'генератор кислорода', 'осушитель сжатого воздуха',
              'фотосепаратор', 'оптический сортировщик', 'рентген инспекция',
              'строительство производственного корпуса']


def queries_kak_v_boyu():
    inds = list(NS.KC_INDUSTRIES) + list(NS.MEYER_INDUSTRIES)
    return ['%s %s' % (t, ind) for t in NS.TRIGGERS[:6] for ind in inds]


ISTOCHNIKI = [
    ('google', lambda: NS.col_google(queries_kak_v_boyu(), DAYS, MAX)),
    ('zakupki', lambda: NS.col_zakupki(ZAKUPKI_KW, DAYS, MAX)),
    ('hh', lambda: NS.col_hh(NS.HH_SIGNALS, '113', DAYS, MAX)),
    ('frp', lambda: NS.col_frp(DAYS, MAX * 3)),
    ('regional', lambda: NS.col_regional(NS._load_feeds_catalog(), DAYS, MAX)),
]

sch = collections.Counter()
itog = {}
for imya, zov in ISTOCHNIKI:
    print('\n' + '=' * 62)
    print('=== %s' % imya)
    try:
        items = zov() or []
    except Exception as e:  # noqa: BLE001
        print('    УПАЛ: %s: %s' % (type(e).__name__, str(e)[:140]))
        print('    ' + traceback.format_exc().splitlines()[-1][:140])
        itog[imya] = {'сырых': 0, 'ошибка': '%s' % type(e).__name__}
        sch['коллектор упал'] += 1
        continue
    klyuchi = set()
    for it in items:
        try:
            klyuchi.add(NS._news_key(it))
        except Exception:  # noqa: BLE001
            pass
    # Сколько прошло бы КАПЕКС-предфильтр (для лент он применяется, для целевых нет)
    kapeks = 0
    for it in items:
        if imya in ('regional', 'google'):
            if NS._CAPEX_KW.search(it.get('title', '') or ''):
                kapeks += 1
        else:
            kapeks += 1
    itog[imya] = {'сырых': len(items), 'уникальных': len(klyuchi),
                  'прошло бы капекс-предфильтр': kapeks}
    print('    сырых %d, уникальных %d, прошло бы предфильтр %d'
          % (len(items), len(klyuchi), kapeks))
    for it in items[:3]:
        print('      · %s' % str(it.get('title') or '')[:104])
        print('        %s' % str(it.get('link') or '')[:104])
    if not items:
        print('    ПУСТО — источник не вернул ничего')

print('\n')
for k, v in itog.items():
    print('REC %-10s %s' % (k, json.dumps(v, ensure_ascii=False)))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
