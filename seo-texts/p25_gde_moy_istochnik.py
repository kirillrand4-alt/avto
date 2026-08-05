# -*- coding: utf-8 -*-
"""Где в базах лежит ярлык «поиск-ЛПР-3с-песочница». Найти, а не предположить.

Прибор искал слово «песочница» в колонках с именами source/istoch/otkuda и не нашёл
ничего. Это либо не та база, либо не та колонка, либо ярлык хранится иначе. Восьмой
раз за смену: я предположила, где лежит величина, вместо того чтобы спросить.

Прибор ищет подстроку по ВСЕМ текстовым колонкам ВСЕХ таблиц обеих баз и печатает, где
она встретилась и сколько раз. Дорого по времени, дёшево по смыслу: ответ будет точным.
"""
import collections
import json
import sqlite3

BAZY = (('centrifugal', 'file:C:/seostat/data/centrifugal.db?mode=ro'),
        ('p25', 'file:C:/seostat/data/p25.db?mode=ro'))
ISKOMOE = ('песочниц', 'поиск-ЛПР', 'поиск-лпр')

for imya, put in BAZY:
    try:
        b = sqlite3.connect(put, uri=True)
        tablicy = [t for (t,) in b.execute("select name from sqlite_master where type='table'")]
    except Exception as e:  # noqa: BLE001
        print('%s: %s' % (imya, e))
        continue
    nashli = collections.Counter()
    primery = {}
    for t in tablicy:
        try:
            polya = [r[1] for r in b.execute('pragma table_info(%s)' % t)]
            stroki = list(b.execute('select %s from %s' % (','.join(polya), t)))
        except Exception:  # noqa: BLE001
            continue
        for r in stroki:
            z = dict(zip(polya, r))
            for k, v in z.items():
                if not isinstance(v, str):
                    continue
                for isk in ISKOMOE:
                    if isk in v:
                        nashli['%s.%s' % (t, k)] += 1
                        primery.setdefault('%s.%s' % (t, k), v[:120])
                        break
    print('=== %s' % imya)
    for k, v in nashli.most_common(12):
        print('   %-28s %6d   пример: %s' % (k, v, primery.get(k, '')[:70]))
    if not nashli:
        print('   не встречается вовсе')
print('ИТОГ ' + json.dumps({'искали': ISKOMOE}, ensure_ascii=False))
