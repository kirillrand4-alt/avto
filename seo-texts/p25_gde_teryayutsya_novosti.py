# -*- coding: utf-8 -*-
"""Стадия A. Четыре коллектора дали НОЛЬ событий. Где именно потеря — три разных места.

Прогон 12:31 дал 653 сырых, 100 капекс, 62 с ИНН, но по коллекторам google 186 сырых → 0
событий, zakupki 58 → 0, frp 6 → 0, hh 0 → 0. «Ноль» — это НЕ диагноз, потому что за ним
стоят три разные поломки, и чинятся они по-разному:

  1. коллектор не вернул ничего        — источник закрыт/сломан/блокирует;
  2. items были, но ключ уже в seen_news — новость забрали раньше (в т.ч. соседняя сессия);
  3. items были и новые, но капекс-фильтр сказал «не наше» — вопрос к фильтру.

2-я сессия дала число, которое делает вторую версию главной: **в seen_news 82 930 ключей**,
и первый забравший закрывает новость для всех остальных навсегда. Значит мой «пустой
источник» может быть «уже съеденным», и это ровно та ошибка, за которую платят выброшенным
источником: закрываешь коллектор, который на самом деле работает.

ЧТО ДЕЛАЕТ ПРИБОР. Зовёт каждый молчащий коллектор напрямую теми же дефолтами, что и
`collect_all`, и по КАЖДОМУ item отвечает на вопрос «а где бы он умер»:

    сырых → уникальных ключей → сколько уже в seen_news → сколько прошло бы капекс

Провайдера не трогает и в seen_news НЕ ПИШЕТ — только читает. Значит ни квоты, ни общего
ресурса не расходует, и запускать его при чужом замке безопасно.

ПРОТОКОЛ: печатает `news_scan.__file__` и путь базы. Замер без имени файла — не замер;
за это уже заплачено полным отзывом Р-001, который я сделала на файле из ветки docs.
"""
import collections
import io
import json
import os
import re
import sqlite3
import sys
import traceback

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

DAYS = 14
MAX = 10
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db']

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
]

print('=== ЧЕМ МЕРЯЮ')
print('news_scan.__file__ = %s' % getattr(NS, '__file__', '?'))

# --- где живёт seen_news и что в нём лежит ------------------------------------------
baza, kluchi = None, set()
for b in BAZY:
    if not os.path.exists(b):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        est = [r[0] for r in cx.execute(
            "select name from sqlite_master where type='table' and name='seen_news'")]
        if not est:
            cx.close()
            continue
        kol = [r[1] for r in cx.execute('pragma table_info(seen_news)')]
        vsego = cx.execute('select count(*) from seen_news').fetchone()[0]
        print('seen_news в %s: строк %d, колонки %s' % (b, vsego, kol))
        polya = [k for k in kol if k.lower() in ('key', 'k', 'news_key', 'hash', 'id')]
        pole = polya[0] if polya else kol[0]
        for r in cx.execute('select %s from seen_news limit 3' % pole):
            print('   образец ключа: %r' % (r[0],))
        kluchi = set(r[0] for r in cx.execute('select %s from seen_news' % pole))
        baza = b
        cx.close()
        break
    except Exception as e:  # noqa: BLE001
        print('   %s: %s' % (b, e))

if baza is None:
    print('ВНИМАНИЕ: таблицы seen_news не нашлось ни в одной базе — версия 2 непроверяема')

# --- как выглядит сам фильтр в бою --------------------------------------------------
try:
    ish = io.open(NS.__file__, encoding='utf-8', errors='replace').read().split('\n')
    print('\n=== где в живом коде трогают seen_news')
    for i, s in enumerate(ish):
        if 'seen_news' in s or '_news_key' in s:
            print('%5d| %s' % (i + 1, s.strip()[:150]))
except Exception as e:  # noqa: BLE001
    print('исходник не прочитался: %s' % e)

# --- сам замер ----------------------------------------------------------------------
itog = {}
for imya, zov in ISTOCHNIKI:
    print('\n' + '=' * 62)
    print('=== %s' % imya)
    try:
        items = zov() or []
    except Exception as e:  # noqa: BLE001
        print('    УПАЛ: %s: %s' % (type(e).__name__, str(e)[:160]))
        print('    ' + traceback.format_exc().splitlines()[-1][:160])
        itog[imya] = {'сырых': 0, 'упал': type(e).__name__}
        continue

    vidal, uzhe, novye = set(), 0, []
    for it in items:
        try:
            k = NS._news_key(it)
        except Exception:  # noqa: BLE001
            k = None
        if k is None or k in vidal:
            continue
        vidal.add(k)
        if k in kluchi:
            uzhe += 1
        else:
            novye.append(it)

    kapeks = [it for it in novye
              if NS._CAPEX_KW.search((it.get('title') or '') + ' ' + (it.get('text') or ''))]
    itog[imya] = {'сырых': len(items), 'уникальных': len(vidal),
                  'уже в seen_news': uzhe, 'новых': len(novye),
                  'из новых прошли бы капекс': len(kapeks)}
    print('    сырых %d → уникальных %d → уже виданы %d → новых %d → капекс %d'
          % (len(items), len(vidal), uzhe, len(novye), len(kapeks)))
    if not items:
        print('    ПУСТО НА ВХОДЕ — источник не вернул ничего, дедуп ни при чём')
    for it in novye[:5]:
        print('      НОВОЕ · %s' % str(it.get('title') or '')[:100])
        print('              %s' % str(it.get('link') or '')[:100])
    for it in items[:3]:
        if it not in novye:
            print('      виданое · %s' % str(it.get('title') or '')[:96])

print('\n')
for k, v in itog.items():
    print('REC %-9s %s' % (k, json.dumps(v, ensure_ascii=False)))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
