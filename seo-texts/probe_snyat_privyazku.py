# -*- coding: utf-8 -*-
"""Снять ложную привязку у 449 человек: они настоящие, но работают НЕ у нас.

Не удаляю и не прячу: человек с именем, должностью и НАЗВАННЫМ работодателем — это данные, а
не мусор. Ложным было только одно — что он наш. Поэтому в панели у таких записей имя остаётся,
а к должности и источнику дописывается, чей он на самом деле, чтобы продавец не звонил ему как
сотруднику нашего предприятия.

Матчинг по паре (ИНН нашего предприятия + ФИО): именно эта пара и была неверной.
"""
import csv
import json
import os
import sqlite3

PUT = r'C:\sender\_ops\3s_VAZHNOE-3s-CHUZHAYA-PRIVYAZKA-449.csv'
rows = list(csv.DictReader(open(PUT, encoding='utf-8-sig'), delimiter=';'))
pary = {}
for r in rows:
    pary[((r.get('nash_inn') or '').strip(), (r.get('fio') or '').strip())] = \
        (r.get('ego_predpriyatie') or '').strip()
print('пар к снятию привязки:', len(pary))

for baza, tabl, pole_post in ((r'C:\seostat\data\centrifugal.db', 'person', 'position'),
                              (r'C:\sender\enrich.db', 'people', 'post')):
    cx = sqlite3.connect(baza)
    pravki = []
    for rid, inn, person, post, src in cx.execute(
            f"select rowid, coalesce(inn,''), coalesce(person,''), coalesce({pole_post},''), "
            f"coalesce(source,'') from {tabl}"):
        ego = pary.get((inn, person.strip()))
        if not ego or 'работает не у нас' in src:
            continue
        pravki.append((f'{post} [работает в «{ego}», не у нас]'[:200],
                       src + f' [ПРИВЯЗКА СНЯТА: в источнике назван «{ego}»]', rid))
    print(f'{baza}: найдено {len(pravki)}')
    if 'PRIMENIT' in os.sys.argv and pravki:
        cx.executemany(f'update {tabl} set {pole_post} = ?, source = ? where rowid = ?', pravki)
        cx.commit()
        print('  снято')
