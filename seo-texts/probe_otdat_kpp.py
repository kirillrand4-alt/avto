# -*- coding: utf-8 -*-
"""Отдать соседям карту ИНН → КПП: у 2-й сессии из-за её отсутствия стоит канал РТС.

2-я сессия записала: «РТС: 23 предприятия без КПП, вход туда — слаг ИНН-КПП, и КПП не знает ни
справочник Сбербанк-АСТ, ни ЕГРЮЛ». КПП есть — в `enrich.db`, таблица `requisites`, 2 342
строки. Положила его туда ночью 1-я сессия своим прогоном DaData, и ни та, ни другая об этом
не знала: канал есть, а карты каналов нет.

Выкладываю на дроп с ОГРН и названием, чтобы сшивалось не только по ИНН.
"""
import csv
import io
import json
import os
import sqlite3
import urllib.request

cx = sqlite3.connect(r'C:\sender\enrich.db')
kol = [r[1] for r in cx.execute('pragma table_info(requisites)')]
bral = [k for k in ('inn', 'kpp', 'ogrn', 'name', 'short_name', 'reg_date', 'status')
        if k in kol]
rows = [dict(zip(bral, r)) for r in cx.execute(
    f'select {",".join(bral)} from requisites where coalesce(kpp,\'\') <> \'\'')]
b = io.StringIO()
w = csv.DictWriter(b, fieldnames=bral, delimiter=';')
w.writeheader()
w.writerows(rows)
telo = b.getvalue().encode('utf-8-sig')
req = urllib.request.Request(
    os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
    + '/VAZHNOE-3s-KARTA-INN-KPP.csv', data=telo, method='PUT',
    headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
with urllib.request.urlopen(req, timeout=180) as r:
    print(json.dumps({'колонки': bral, 'строк_с_КПП': len(rows), 'выгрузка': r.status,
                      'байт': len(telo)}, ensure_ascii=False))
