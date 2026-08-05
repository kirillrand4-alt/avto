# -*- coding: utf-8 -*-
"""Фактическая схема p25.db с примерами значений. Шестое имя поля за смену не угадываю.

Прибор `p25_tehnari_iz_bazy.py` вернул 16 технарей с пустой колонкой «человек»: имя
искалось по списку ('fio','name','chelovek','imya'), а называется оно иначе. Пятый раз
за смену я угадала имя поля вместо того, чтобы посмотреть.

И более важное: сборщик входа обратного хода читает только CSV-файлы. Сама база
person/contact как источник имён им НЕ ЧИТАЕТСЯ ни разу — а в ней 56 технарей с
названной должностью и без мобильного, то есть готовые цели канала.
"""
import json
import sqlite3

b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
for (t,) in b.execute("select name from sqlite_master where type='table' order by name"):
    polya = [(r[1], r[2]) for r in b.execute('pragma table_info(%s)' % t)]
    try:
        n = b.execute('select count(*) from %s' % t).fetchone()[0]
    except Exception:  # noqa: BLE001
        n = -1
    print('=== %s  строк %d' % (t, n))
    print('    поля: %s' % ', '.join('%s(%s)' % p for p in polya))
    try:
        stroka = b.execute('select %s from %s limit 1'
                           % (','.join(p[0] for p in polya), t)).fetchone()
        if stroka:
            print('    пример: %s' % json.dumps(
                {p[0]: str(v)[:48] for p, v in zip(polya, stroka)},
                ensure_ascii=False)[:520])
    except Exception as e:  # noqa: BLE001
        print('    пример не прочёлся: %s' % e)
print('ИТОГ ' + json.dumps({'схема снята': True}, ensure_ascii=False))
