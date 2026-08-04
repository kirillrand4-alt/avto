# -*- coding: utf-8 -*-
"""Пометить номер из блока реквизитов как линию предприятия, а не как контакт человека.

Случай владельца: у Лебедя О.А. в карточке стоял «мобильный +7 949 314 55 05» с ролью
«технический ЛПР». Номер взят из реквизитов заказчика в проекте договора — это линия юрлица.
Имя при этом доказано (подписант по доверенности), поэтому запись не удаляется: остаётся
человек с должностью и БЕЗ личного номера, а номер переносится в подпись «линия предприятия».
"""
import os
import re
import sqlite3

CEL = '9493145505'
for baza, tabl in ((r'C:\seostat\data\centrifugal.db', 'person'),
                   (r'C:\sender\enrich.db', 'people')):
    cx = sqlite3.connect(baza)
    pravki = []
    for rid, person, phone, src in cx.execute(
            f"select rowid, coalesce(person,''), coalesce(phone,''), coalesce(source,'') "
            f'from {tabl}'):
        if re.sub(r'\D', '', phone)[-10:] != CEL or 'реквизит' in src:
            continue
        pravki.append((src + ' [номер из блока РЕКВИЗИТОВ договора — линия предприятия, '
                             'не личный номер подписанта]', rid))
    print(f'{baza}: найдено {len(pravki)}')
    if 'PRIMENIT' in os.sys.argv and pravki:
        cx.executemany(f'update {tabl} set source = ? where rowid = ?', pravki)
        cx.commit()
        print('  помечено')
