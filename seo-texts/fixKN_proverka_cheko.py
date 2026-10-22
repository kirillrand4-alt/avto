# -*- coding: utf-8 -*-
r"""fixKN (22.10): где в каталоге КЦ остались контакты checko / старые – по группам компаний. Только чтение.
Аргумент – часть домена почты или номер для поиска конкретной компании (номера не печатаются, только ИНН и счётчики).

    python3 zapusk_na_servere.py fixKN_proverka_cheko.py snos.ru
"""
import collections
import json
import os
import re
import sqlite3
import sys

KAT = r'C:\seostat\data\centrifugal.db'
SALES = r'C:\seostat\data\centro_sales.db'
pak = json.load(open(r'C:\seostat\drop\drop-storage\KN-paket.json', encoding='utf-8'))
zam, ko = set(pak['inn_zamena']), set(pak['inn_ko'])
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
skryt = {r[0] for r in s.execute("SELECT DISTINCT inn FROM hidden_item WHERE kind='company'")}
asg = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
st = {(a, b): c for a, b, c in s.execute('SELECT inn, username, call_result FROM company_state')}
imp = {r[0] for r in k.execute('SELECT inn FROM import_fixKN')}
print('в каталоге отмечено заменённых (import_fixKN):', len(imp), '; совпадает с пакетом:', imp == zam)
iskat = sys.argv[1] if len(sys.argv) > 1 else ''
if iskat:
    d = re.sub(r'\D', '', iskat)
    inns = {r[0] for r in k.execute('SELECT inn, value FROM contact') if (iskat.lower() in str(r[1]).lower()) or (len(d) >= 7 and d in re.sub(r'\D', '', str(r[1])))}
    for inn in sorted(inns):
        u = asg.get(inn, '')
        nazv = (k.execute('SELECT predpriyatie FROM company WHERE inn=?', (inn,)).fetchone() or [''])[0]
        ist = collections.Counter(str(r[0])[:30] for r in k.execute('SELECT source FROM contact WHERE inn=?', (inn,)))
        print('ИНН %s «%s»: в «КО» %s, в пакете замены %s, заменён %s, скрыта %s, менеджер %s, статус %s; источники контактов: %s' % (
            inn, nazv[:50], inn in ko, inn in zam, inn in imp, inn in skryt, u, st.get((inn, u)) or 'new', ist.most_common(5)))
gr = collections.Counter()
for inn, src in k.execute('SELECT inn, source FROM contact'):
    if inn in skryt:
        continue
    g = 'заменённые (417)' if inn in zam else ('«КО» без новых данных (106)' if inn in ko else 'не «КО» (в т.ч. «Взял в работу»)')
    gr[(g, 'checko' if 'чеко' in str(src).lower() or 'checko' in str(src).lower() else 'прочие')] += 1
for kk, n in sorted(gr.items()):
    print('  видимые, %-40s %-8s контактов %d' % (kk + (n,)))
