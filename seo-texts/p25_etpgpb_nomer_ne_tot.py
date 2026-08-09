# -*- coding: utf-8 -*-
"""Проверяю догадку: в базе лежит НЕ тот номер, из которого строится адрес ЭТП ГПБ.

Мерка с контролем заработала (контроль 0 из 6, рабочие 6 из 6), и в заголовках открылось
неожиданное:

    адрес  /procedure/tender/etp/738892-postavka-turbokompressora-.../
    титул  «ГП302295 Тендер на закупку Поставка турбокомпрессора воздушного…»

То есть 738892 — внутренний идентификатор страницы, а ГП302295 — реестровый номер площадки.
В нашей таблице `tenders` лежит номер вида «ГП302295». Если догадка верна, построить адрес
из нашего номера НЕЛЬЗЯ в принципе, и 26 873 строки ЭТП ГПБ так не доказать.

Смотрю в самой базе: есть ли там номера из заголовков и есть ли номера из адресов.
"""
import re
import sqlite3

BAZA = r'C:\seostat\drop\drop-storage\atlas_copco.db'
IZ_ZAGOLOVKOV = ['ГП302295', 'ГП219976', 'ГП124211']
IZ_ADRESOV = ['738892', '657160', '573792']

cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
print('########## ЕСТЬ ЛИ В tenders НОМЕРА ИЗ ЗАГОЛОВКОВ (реестровые номера площадки)')
for n in IZ_ZAGOLOVKOV:
    c = cx.execute('select count(*) from tenders where reg_number = ?', (n,)).fetchone()[0]
    print('  %-12s строк %d' % (n, c))
print('\n########## ЕСТЬ ЛИ НОМЕРА ИЗ АДРЕСОВ (внутренние идентификаторы страниц)')
for n in IZ_ADRESOV:
    c = cx.execute('select count(*) from tenders where reg_number = ? or reg_number = ?',
                   (n, 'ГП' + n)).fetchone()[0]
    print('  %-12s строк %d' % (n, c))
print('\n########## ОБРАЗЦЫ reg_number у площадки etpgpb')
for r in cx.execute("select reg_number, substr(title,1,60) from tenders "
                    "where platform like 'etpgpb%' limit 8"):
    print('  %-14s %s' % (r[0], r[1]))
print('\n########## СКОЛЬКО СТРОК ЭТП ГПБ ИМЕЮТ ССЫЛКУ УЖЕ СЕЙЧАС')
est = cx.execute("select count(*) from tenders where platform like 'etpgpb%' "
                 "and (title like '%http%' or reg_number like '%http%')").fetchone()[0]
vsego = cx.execute("select count(*) from tenders where platform like 'etpgpb%'").fetchone()[0]
print('  всего строк etpgpb %d, из них со ссылкой в тексте %d' % (vsego, est))
cx.close()
print('ИТОГ {"смотрела": "совпадают ли номера базы с номерами адресов"}')
