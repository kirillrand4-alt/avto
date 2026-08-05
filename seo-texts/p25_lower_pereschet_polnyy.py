# -*- coding: utf-8 -*-
"""Пересчитать ВСЁ, что когда-либо считалось через SQL lower() по кириллице.

ПОЧЕМУ ЭТО НЕ МЕЛОЧЬ. `sqlite3.lower()` понижает только ASCII. Запрос
`lower(dolzhnost) like '%инженер%'` не находит «Главный Инженер» с большой буквы — и
не сообщает об этом, а честно возвращает меньшее число. 1-я сессия намерила у себя
72 против 234 в Python: втрое.

Такой промах не виден никак: ошибки нет, предупреждения нет, число выглядит ответом.
Поэтому пересчитываю не «подозрительные места», а ВСЕ роли и признаки, которые у нас
считаются по русским словам, и печатаю обе величины рядом.

Прибор ничего не чинит в базе — он ИЗМЕРЯЕТ РАЗНИЦУ. Чинить надо там, где число
использовалось, а для этого сперва надо знать, где и насколько соврало.
"""
import collections
import json
import re
import sqlite3

BAZY = (('p25', 'file:C:/seostat/data/p25.db?mode=ro'),
        ('centrifugal', 'file:C:/seostat/data/centrifugal.db?mode=ro'),
        ('enrich', 'file:C:/seostat/data/enrich.db?mode=ro'))
SLOVA = ('инженер', 'механик', 'энергетик', 'технолог', 'директор', 'начальник',
         'главный', 'снабжен', 'закупк', 'компрессор', 'центробеж')

itog = {}
for imya, put in BAZY:
    try:
        b = sqlite3.connect(put, uri=True)
        tablicy = [t for (t,) in b.execute(
            "select name from sqlite_master where type='table'")]
    except Exception as e:  # noqa: BLE001
        itog[imya] = 'база недоступна: %s' % e
        continue
    # КОНТРОЛЬ ПРИБОРА. Ноль расхождений бывает двух родов: «SQL и Python согласны» и
    # «прибор не проверил ничего». Различить их можно только счётом проверок, поэтому
    # он печатается всегда. Ноль при нуле проверок — не ответ, а молчание.
    razlichiya, proverok, s_nahodkami = [], 0, 0
    for t in tablicy:
        try:
            polya = [r[1] for r in b.execute('pragma table_info(%s)' % t)]
        except Exception:  # noqa: BLE001
            continue
        # ВСЕ колонки, а не отобранные по имени. Первый заход фильтровал имена колонок
        # шаблоном `dolzh|post|rol|nazv|...` и сделал 132 проверки, из которых слово
        # встретилось в ТРЁХ: искала не там. Это опять узкий список целей при широком
        # приборе — четвёртый раз за смену. Колонок в базе немного, перебрать все дешевле,
        # чем гадать, как названа нужная.
        tekstovye = list(polya)
        for pole in tekstovye:
            for slovo in SLOVA:
                try:
                    sql_n = b.execute(
                        'select count(*) from %s where lower(%s) like ?' % (t, pole),
                        ('%' + slovo + '%',)).fetchone()[0]
                except Exception:  # noqa: BLE001
                    continue
                if sql_n is None:
                    continue
                try:
                    py_n = 0
                    for (v,) in b.execute('select %s from %s' % (pole, t)):
                        if v and slovo in str(v).lower():
                            py_n += 1
                except Exception:  # noqa: BLE001
                    continue
                proverok += 1
                if py_n:
                    s_nahodkami += 1
                if py_n != sql_n:
                    razlichiya.append({
                        'таблица': t, 'колонка': pole, 'слово': slovo,
                        'SQL lower': sql_n, 'Python lower': py_n,
                        'потеряно': py_n - sql_n,
                        'во сколько раз': round(py_n / sql_n, 2) if sql_n else None})
    razlichiya.sort(key=lambda x: -x['потеряно'])
    itog[imya] = {'таблиц': len(tablicy), 'ПРОВЕРОК СДЕЛАНО': proverok,
                  'из них слово вообще встретилось': s_nahodkami,
                  'расхождений': len(razlichiya),
                  'потеряно строк всего': sum(x['потеряно'] for x in razlichiya),
                  'худшие': razlichiya[:8]}

for imya, v in itog.items():
    print('=== %s' % imya)
    if isinstance(v, str):
        print('   ' + v)
        continue
    for x in v['худшие']:
        print('   %-18s %-16s «%-11s» SQL %6d  Python %6d  потеряно %6d  x%s'
              % (x['таблица'][:18], x['колонка'][:16], x['слово'],
                 x['SQL lower'], x['Python lower'], x['потеряно'], x['во сколько раз']))
print('ИТОГ ' + json.dumps({k: (v if isinstance(v, str)
                                else {kk: vv for kk, vv in v.items() if kk != 'худшие'})
                            for k, v in itog.items()}, ensure_ascii=False))
