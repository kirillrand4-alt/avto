# -*- coding: utf-8 -*-
"""Схема каталога панели и как код его читает — перед заменой базы на мейеровскую.

Новую базу собираю В ТОЙ ЖЕ СХЕМЕ, что centrifugal.db: тогда код панели не меняется, а
подмена — это строка в .env. Для этого нужно знать: таблицы и колонки, формат значений
(как хранится телефон, роль, признаки закупщика/техника), какие колонки читает модуль
каталога, и как панель считает приоритет (company_score) и раздаёт компании (assign_new).
"""
import io
import json
import os
import re
import sqlite3

KOREN = r'C:\centro2'
OTCHET = r'C:\seostat\drop\drop-storage\razbor-kataloga.txt'
vyhod = []


def pishi(s=''):
    vyhod.append(str(s))


c = sqlite3.connect('file:%s?mode=ro' % os.path.join(KOREN, 'data', 'centrifugal.db'), uri=True)
c.row_factory = sqlite3.Row
pishi('########## СХЕМА centrifugal.db')
for r in c.execute("select type, name, sql from sqlite_master where sql is not null order by type, name"):
    n = ''
    if r['type'] == 'table':
        n = ' — строк %d' % c.execute('select count(*) from "%s"' % r['name']).fetchone()[0]
    pishi('--- %s %s%s' % (r['type'], r['name'], n))
    pishi('    ' + re.sub(r'\s+', ' ', r['sql'])[:1500])

for t in ('company', 'contact', 'person', 'fact', 'company_source', 'signal'):
    try:
        row = c.execute('select * from "%s" limit 1' % t).fetchone()
    except sqlite3.OperationalError:
        continue
    if row:
        pishi()
        pishi('--- образец строки %s' % t)
        for k in row.keys():
            pishi('    %-28s %s' % (k, repr(row[k])[:120]))
# распределения важных полей контакта
pishi()
for t, pole in (('contact', 'kind'), ('contact', 'phone_type'), ('contact', 'role'),
                ('contact', 'source'), ('company', 'verdikt'), ('company', 'tipy_mashin')):
    try:
        raskl = c.execute('select %s, count(*) from %s group by 1 order by 2 desc limit 10' % (pole, t)).fetchall()
        pishi('%s.%s: %s' % (t, pole, [(str(a)[:40], b) for a, b in raskl]))
    except sqlite3.OperationalError as e:
        pishi('%s.%s: нет (%s)' % (t, pole, e))

# ---- модуль каталога
pishi()
pishi('########## МОДУЛЬ КАТАЛОГА')
kand = []
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in fajly:
        if f.endswith('.py') and ('catalog' in f or 'centro' in f):
            kand.append(os.path.join(kor, f))
for p in kand:
    t = io.open(p, encoding='utf-8', errors='replace').read()
    if 'def list_companies' in t or 'def contacts' in t:
        pishi('=== %s (%d знаков)' % (p, len(t)))
        for i, l in enumerate(t.splitlines(), 1):
            if re.search(r'^def |SELECT|select |FROM |from company|from contact|JOIN|WHERE|'
                         r'is_purchaser|is_tech|has_role|kind|phone_type', l):
                pishi('   %4d: %s' % (i, l.rstrip()[:175]))

# ---- приоритет и раздача
pishi()
pishi('########## company_score / assign_new / _okved_ves')
for p in (os.path.join(KOREN, 'app', 'services', 'centro_sales.py'),
          os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')):
    t = io.open(p, encoding='utf-8', errors='replace').read().splitlines()
    for imya in ('def company_score', 'def assign_new', 'def _okved_ves', 'def _queue_rank'):
        for i, l in enumerate(t):
            if l.startswith(imya):
                pishi('--- %s:%d' % (os.path.basename(p), i + 1))
                for j in range(i, min(len(t), i + 70)):
                    if j > i and t[j].startswith('def '):
                        break
                    pishi('   %4d: %s' % (j + 1, t[j].rstrip()[:175]))

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
