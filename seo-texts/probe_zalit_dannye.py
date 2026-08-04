# -*- coding: utf-8 -*-
"""Что из отданных мне файлов ЕЩЁ НЕ В ПАНЕЛИ — считаю прежде, чем заливать.

ПОВОД. Владелец спросил, что могло бы работать и не работает. Самое дешёвое из незанятого —
не новый сбор, а данные, которые мне уже отдали и которые лежат неразобранными:
    DLYA-3S-FIO-bez-lichnogo-nomera-2s.csv    710 человек, у 653 городской телефон, 674 почты
    DOLIVKA-lyudey-3s-ot-1-sessii.csv          83 человека, 38 телефонов, 11 мобильных
    DOLIVKA-tenderpro-3s-ot-1-sessii.csv        3 человека
Это 796 человек и 694 контакта, добытых чужими прогонами. Ни один поисковый канал для них не
нужен — нужна сверка и заливка.

СЧИТАЮ ПРИРОСТ, А НЕ ОБЪЁМ. Правило 2-й сессии, которое мы приняли обоюдно: «считает и
называет ПРИНИМАЮЩИЙ». Объявить 796 человек прибавкой, не сверив с тем, что уже лежит, — это
приписка. Поэтому здесь: сколько пар (ИНН + фамилия) новые, сколько номеров новые, и у
скольких предприятий досягаемость реально вырастет.
"""
import collections
import csv
import json
import re
import sqlite3

csv.field_size_limit(10 ** 7)
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')


def fam(s):
    ch = re.split(r'[\s.,]+', (s or '').strip())
    return ch[0].lower().replace('ё', 'е') if ch and ch[0] else ''


def nom(t):
    c = re.sub(r'\D', '', t or '')
    return c[-10:] if len(c) >= 10 else ''


est_par = set()
est_nom = collections.defaultdict(set)
for inn, person, phone in cx.execute(
        "select coalesce(inn,''), coalesce(person,''), coalesce(phone,'') from person"):
    if fam(person):
        est_par.add((inn, fam(person)))
    if nom(phone):
        est_nom[inn].add(nom(phone))

FAJLY = [(r'C:\sender\_ops\3s_DLYA-3S-FIO-bez-lichnogo-nomera-2s.csv',
          'chelovek', ['telefon_gorodskoy']),
         (r'C:\sender\_ops\3s_DOLIVKA-lyudey-3s-ot-1-sessii.csv', 'fio', ['telefon']),
         (r'C:\sender\_ops\3s_DOLIVKA-tenderpro-3s-ot-1-sessii.csv', 'fio', ['telefon'])]
o = {}
novye_lyudi, novye_nomera, inn_zatronuto = 0, 0, set()
for put, pole_imya, polya_tel in FAJLY:
    import os
    if not os.path.exists(put):
        o[put.split('\\')[-1]] = 'файла нет на сервере'
        continue
    rows = list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'))
    nl = nn = 0
    for r in rows:
        inn = (r.get('inn') or '').strip()
        f = fam(r.get(pole_imya))
        if inn and f and (inn, f) not in est_par:
            nl += 1
            est_par.add((inn, f))
            inn_zatronuto.add(inn)
        for k in polya_tel:
            t = nom(r.get(k))
            if t and t not in est_nom[inn]:
                nn += 1
                est_nom[inn].add(t)
                inn_zatronuto.add(inn)
    novye_lyudi += nl
    novye_nomera += nn
    o[put.split('\\')[-1]] = {'строк': len(rows), 'НОВЫХ людей': nl, 'НОВЫХ номеров': nn}
o['итого_новых_людей'] = novye_lyudi
o['итого_новых_номеров'] = novye_nomera
o['предприятий_затронуто'] = len(inn_zatronuto)
# У скольких из затронутых сейчас вообще нет телефона — им прибавка меняет очередь.
bez_tel = {r[0] for r in cx.execute(
    "select inn from company where inn not in "
    "(select inn from person where coalesce(phone,'') <> '')")}
o['из_них_сейчас_БЕЗ_единого_телефона'] = len(inn_zatronuto & bez_tel)
print(json.dumps(o, ensure_ascii=False, indent=1))
