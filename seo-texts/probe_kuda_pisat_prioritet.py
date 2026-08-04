# -*- coding: utf-8 -*-
"""Куда писать приоритет, чтобы он пережил пересборку базы.

ПОВОД — чужая ошибка, записанная 1-й сессией и стоившая им целой правки: они писали
`UPDATE contact` прямо в `centrifugal.db`, а она read-only и пересобирается из enrich.db,
поэтому изменения откатывались следующей сборкой. Повторять это нельзя.

Смотрю: какие таблицы есть в centro_sales.db (она НЕ пересобирается — там живут решения
продавца), какие поля приоритета есть в company, и по чему панель сортирует очередь.
"""
import json
import sqlite3

o = {}
for imya, put in (('centro_sales', r'C:\seostat\data\centro_sales.db'),
                  ('centrifugal', r'C:\seostat\data\centrifugal.db')):
    cx = sqlite3.connect(put)
    t = {}
    for (n,) in cx.execute("select name from sqlite_master where type='table' order by name"):
        kol = [r[1] for r in cx.execute(f'pragma table_info("{n}")')]
        t[n] = {'строк': cx.execute(f'select count(*) from "{n}"').fetchone()[0],
                'колонки': kol}
    o[imya] = t
# Чем заполнены поля приоритета сейчас.
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
for pole in ('moy_prioritet', 'vazhnost_pokupki', 'dostupnost_kontakta', 'prioritet_pochemu'):
    try:
        o[f'заполнено_{pole}'] = cx.execute(
            f'select count(*) from company where coalesce("{pole}",\'\') <> \'\''
        ).fetchone()[0]
        o[f'пример_{pole}'] = cx.execute(
            f'select "{pole}" from company where coalesce("{pole}",\'\') <> \'\' limit 3'
        ).fetchall()
    except Exception as e:  # noqa: BLE001
        o[f'заполнено_{pole}'] = f'{type(e).__name__}'
print(json.dumps(o, ensure_ascii=False, indent=1)[:4000])
