# -*- coding: utf-8 -*-
r"""Исправитель E1 (регионы, пояса, сегменты, пометки): только ЧТЕНИЕ.

Кладёт на дроп:
  fixE1_razvedka.json – схема таблицы company и поля зоны E1 по всем компаниям
                         (регион, пояс, сегменты, ОКВЭД, адрес, статус ЕГРЮЛ, Битрикс);
  fixE1_kod.zip       – текущие routes_centro_sales.py, centro_catalog.py, шаблоны.
Ничего не пишет ни в базы, ни в код панели.

    python3 zapusk_na_servere.py fixE1_razvedka.py
"""
import io
import json
import os
import sqlite3
import zipfile

KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
DROP = r'C:\seostat\drop\drop-storage'

k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
shema = [list(r) for r in k.execute('PRAGMA table_info(company)')]
kol = [r[1] for r in shema]
nuzhno = [c for c in kol if any(s in c for s in (
    'inn', 'predpr', 'name', 'region', 'chas', 'segment', 'popad', 'okved', 'adres', 'status', 'bitrix',
    'bazy', 'otrasl', 'sayt', 'gorod', 'pometk', 'ochered'))]
rows = [{c: r[c] for c in nuzhno} for r in k.execute('select * from company')]
tablicy = [r[0] for r in k.execute("select name from sqlite_master where type='table'")]
out = {'shema': shema, 'kolonki': nuzhno, 'tablicy': tablicy, 'rows': rows}
io.open(os.path.join(DROP, 'fixE1_razvedka.json'), 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False))
print('компаний %d, колонок company %d, взято %d' % (len(rows), len(kol), len(nuzhno)))
print(nuzhno)

z = zipfile.ZipFile(os.path.join(DROP, 'fixE1_kod.zip'), 'w', zipfile.ZIP_DEFLATED)
for p in (os.path.join(APP, 'api', 'routes_centro_sales.py'), os.path.join(APP, 'services', 'centro_catalog.py'),
          os.path.join(APP, 'services', 'centro_sales.py'), os.path.join(APP, 'web.py')):
    if os.path.exists(p):
        z.write(p, os.path.basename(p))
T = os.path.join(APP, 'templates')
for f in os.listdir(T):
    if f.startswith(('centro', '_ochered', '_statblok')):
        z.write(os.path.join(T, f), 'templates/' + f)
z.close()
print('ok')
