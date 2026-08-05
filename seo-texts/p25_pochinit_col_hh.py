# -*- coding: utf-8 -*-
"""Починить `col_hh`: два заголовка. И заодно проверить чужое число по `inn_conf` своим прибором.

ЧТО ЧИНЮ И ПОЧЕМУ ЭТО ТОЧНО ПОЧИНКА, А НЕ ДОГАДКА. Замер на живом сервере:

    без заголовков (как сейчас в col_hh)        403 Forbidden
    только HH-User-Agent, без токена            403 Forbidden
    HH_APP_TOKEN из окружения + HH-User-Agent   200, найдено 214 вакансий

1-я сессия проверила независимо: `api.hh.ru/vacancies?text=компрессор` -> 200, найдено
1991, и по всей очереди 28 сцепок из 28 верны. То есть канал не мёртв, он закрыт не с
той двери: коллектор идёт в публичную выдачу, а она с нашего IP заперта.

КАК ЧИНЮ — правило для чужого файла, выведенное из своих же поломок:
  * бэкап с отметкой времени ДО правки;
  * замена ТОЧНОЙ строки, найденной внутри исходника самой `col_hh`, а не по всему файлу
    (та же строка `_get(url, ...)` может стоять в других коллекторах);
  * `py_compile` после правки — синтаксис проверяет машина, не глаза;
  * если совпадений не ровно одно — НЕ ПРАВЛЮ и печатаю сколько нашлось.

ЗАМЕР ДО/ПОСЛЕ на одних и тех же запросах, иначе это не починка, а надежда.

Токен нигде не печатается — только факт наличия и длина.
"""
import importlib
import io
import json
import os
import py_compile
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

PUT = NS.__file__
print('правлю живой файл: %s' % PUT)

# --- 0. чужое число проверяю своим прибором ------------------------------------------
import sqlite3  # noqa: E402
print('\n=== ПРОВЕРКА ЧУЖОГО ЧИСЛА: inn_conf в signals (правка 1-й сессии)')
try:
    cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
    kol = [r[1] for r in cx.execute('pragma table_info(signals)')]
    print('  колонки signals: %s' % kol)
    if 'inn_conf' in kol:
        for v, n in cx.execute(
                "select case when inn_conf is null or inn_conf='' then '(метки нет)'"
                " else inn_conf end, count(*) from signals group by 1 order by 2 desc"):
            print('    %-14s %5d' % (v, n))
        n_inn = cx.execute("select count(distinct inn) from signals where inn_conf='low'"
                           ).fetchone()[0]
        print('    разных ИНН с low: %d' % n_inn)
    else:
        print('  колонки inn_conf НЕТ — правка не доехала')
    cx.close()
except Exception as e:  # noqa: BLE001
    print('  не прочиталось: %s' % str(e)[:140])

# --- 1. замер ДО ----------------------------------------------------------------------
print('\n=== ЗАМЕР ДО ПРАВКИ')
try:
    do = NS.col_hh(NS.HH_SIGNALS, '113', 14, 10) or []
except Exception as e:  # noqa: BLE001
    do = []
    print('  col_hh упал: %s' % str(e)[:140])
print('  col_hh вернул items: %d' % len(do))
print('  HH_APP_TOKEN в окружении: %s (длина %d)'
      % (bool(os.environ.get('HH_APP_TOKEN')), len(os.environ.get('HH_APP_TOKEN', ''))))

# --- 2. правка ------------------------------------------------------------------------
import inspect  # noqa: E402
ish = io.open(PUT, encoding='utf-8').read()
telo = inspect.getsource(NS.col_hh)
STAROE = "d = json.loads(_get(url, headers={'Accept': 'application/json'}) or '{}')"
NOVOE = ("_hdr = {'Accept': 'application/json',\n"
         "                    'HH-User-Agent': 'RuspromNewsScan/1.0 (kirillrand4@gmail.com)'}\n"
         "            _tok = os.environ.get('HH_APP_TOKEN', '')\n"
         "            if _tok:\n"
         "                _hdr['Authorization'] = 'Bearer ' + _tok\n"
         "            # Без токена публичная выдача hh с серверного IP отвечает 403 на всё,\n"
         "            # и коллектор молча даёт ноль. Замер: без заголовков 403, только с\n"
         "            # HH-User-Agent 403, с токеном 200 и 214 вакансий по одному запросу.\n"
         "            d = json.loads(_get(url, headers=_hdr) or '{}')")

skolko_v_tele = telo.count(STAROE)
skolko_v_fayle = ish.count(STAROE)
print('\n=== ПРАВКА')
print('  искомая строка: в теле col_hh %d раз, во всём файле %d раз'
      % (skolko_v_tele, skolko_v_fayle))

if skolko_v_tele != 1:
    print('  НЕ ПРАВЛЮ: в теле col_hh не ровно одно совпадение')
elif skolko_v_fayle != 1:
    print('  НЕ ПРАВЛЮ: строка встречается в файле %d раз — задену чужой коллектор'
          % skolko_v_fayle)
elif 'HH-User-Agent' in ish:
    print('  УЖЕ ПОЧИНЕНО кем-то: HH-User-Agent в файле есть, не трогаю')
else:
    bak = PUT + '.bak-3s-%d' % int(time.time())
    io.open(bak, 'w', encoding='utf-8').write(ish)
    print('  бэкап: %s' % bak)
    io.open(PUT, 'w', encoding='utf-8').write(ish.replace(STAROE, NOVOE))
    try:
        py_compile.compile(PUT, doraise=True)
        print('  py_compile: синтаксис в порядке')
    except Exception as e:  # noqa: BLE001
        io.open(PUT, 'w', encoding='utf-8').write(ish)
        print('  СИНТАКСИС СЛОМАЛСЯ, откатила: %s' % str(e)[:200])

# --- 3. замер ПОСЛЕ -------------------------------------------------------------------
print('\n=== ЗАМЕР ПОСЛЕ ПРАВКИ (модуль перезагружен)')
try:
    importlib.reload(NS)
    posle = NS.col_hh(NS.HH_SIGNALS, '113', 14, 10) or []
except Exception as e:  # noqa: BLE001
    posle = []
    print('  упал: %s: %s' % (type(e).__name__, str(e)[:160]))
print('  col_hh вернул items: %d' % len(posle))
for it in posle[:10]:
    print('    · %s' % str(it.get('title') or '')[:120])
    print('      %s' % str(it.get('link') or '')[:100])

print('\nИТОГ ' + json.dumps({'файл': PUT, 'до': len(do), 'после': len(posle)},
                             ensure_ascii=False))
