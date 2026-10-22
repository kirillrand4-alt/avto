# -*- coding: utf-8 -*-
r"""fixKN (22.10): разведка перед заменой контактов компаний «КО» в каталоге КЦ. Только чтение (sqlite mode=ro).

Схема таблиц contact / person каталога C:\seostat\data\centrifugal.db, сколько контактов и людей сейчас у компаний «КО»
(523 ИНН из KN-inn.json на дропе) – с новыми контактами и без, какие поля company про телефоны заполнены. Номера не выводятся.

    python3 zapusk_na_servere.py fixKN_razvedka.py
"""
import collections
import json
import os
import sqlite3

KAT = r'C:\seostat\data\centrifugal.db'
DROP = r'C:\seostat\drop\drop-storage'
d = json.load(open(os.path.join(DROP, 'KN-inn.json'), encoding='utf-8'))
ko, novye = set(d['ko']), set(d['novye'])
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
print('каталог: %.1f МБ, таблицы: %s' % (os.path.getsize(KAT) / 2**20, [r[0] for r in k.execute("SELECT name FROM sqlite_master WHERE type='table'")]))
for t in ('contact', 'person'):
    kol = [r[1] for r in k.execute('PRAGMA table_info(%s)' % t)]
    print('\n%s: колонки %s' % (t, kol))
    print('   индексы:', [r[1] for r in k.execute('PRAGMA index_list(%s)' % t)])
    vse = k.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]
    po = collections.Counter()
    for (inn,) in k.execute('SELECT inn FROM %s' % t):
        inn = str(inn)
        po['КО с новыми' if inn in novye else ('КО без новых' if inn in ko else 'прочие')] += 1
    print('   строк всего %d; %s' % (vse, dict(po)))
    if t == 'contact':
        for pole in ('kind', 'phone_type', 'source'):
            if pole in kol:
                print('   %s у КО: %s' % (pole, collections.Counter(
                    str(r[1])[:40] for r in k.execute('SELECT inn, %s FROM contact' % pole) if str(r[0]) in ko).most_common(8)))
    if t == 'person':
        print('   пример полей person у КО (без значений):', [c for c in kol])
kol = [r[1] for r in k.execute('PRAGMA table_info(company)')]
tel = [c for c in kol if any(x in c for x in ('telef', 'phone', 'pocht', 'n_', 'has_', 'lyud', 'tehnich', 'nomer'))]
print('\ncompany, поля про контакты:', tel)
for c in tel:
    n = sum(1 for (inn, v) in k.execute('SELECT inn, "%s" FROM company' % c) if str(inn) in ko and v not in (None, '', 0))
    print('   %-32s заполнено у КО: %d' % (c, n))
bez = ko - novye
print('\nКО без новых контактов: %d; из них сейчас с контактами в панели: %d' % (
    len(bez), len({str(r[0]) for r in k.execute('SELECT inn FROM contact')} & bez)))
