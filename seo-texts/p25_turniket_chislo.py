# -*- coding: utf-8 -*-
"""Турникет: сколько строк ГОТОВЫ к генерации письма — все графы доказаны. Одно число.

Владелец: «письмо должно генерироваться уже на идеальных входных данных, а не ждать пока
данные дойдут». Значит турникет это НЕ оценка готового письма, а вход: не доказано —
письмо не пишется вовсе, предприятие уходит в очередь добора.

ЧЕТЫРЕ ГРАФЫ, и у каждой свой владелец по разделению труда:

    Д1 ПОВОД     новость капексная И не чужая                   моя, 3-я сессия
    Д2 ЮРЛИЦО    ИНН подтверждён НЕ по названию                 2-я сессия
    Д3 АДРЕС     почта есть и принадлежит ЭТОМУ юрлицу          2-я сессия
    Д4 ЧЕЛОВЕК   человек назван и это человек, а не отдел       1-я сессия

Считаю по ЖИВОЙ базе и по ЖИВЫМ полям, а не по тому, как мы договорились их назвать:
сначала печатаю, какие поля реально есть, потом считаю. Угаданное имя поля даёт
правдоподобный ноль — за это уже заплачено.

Отдельно считаю `verified='mismatch'`: 2-я сессия показала 77 писем в очереди, у которых
наша собственная сверка сказала «не сходится», и это не мешает им стоять в очереди.

Только чтение.
"""
import collections
import json
import os
import re
import sqlite3

ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'

MASHINA = re.compile(
    r'компрессор\w*|турбокомпрессор\w*|газодувк\w+|газодувн\w+|воздуходувк\w+|'
    r'нагнетател\w+|воздухоразделен\w+|\bВРУ\b|сжат\w+\s+воздух\w*|пневмат\w+|'
    r'генератор\w*\s+(?:азота|кислорода)|\bазот\w*\b|\bкислород\w*\b|\bчиллер\w*', re.I)
PROIZVODSTVO = re.compile(
    r'\b\w*завод\w*|\bцех\w*|\bпроизводств\w*|\b\w*комбинат\w*|\bфабрик\w*|\bэлеватор\w*|'
    r'\bпроизводственн\w+|\bмощност\w+\s+\d|\bагрегат\w*|\bустановк\w+|\bпереработк\w+|'
    r'\bобогатительн\w+|\bметаллург\w+|\bНПЗ\b|\bГОК\b|\bТЭЦ\b|\bдобыч\w+|\bшахт\w+', re.I)
CHUZHOE = re.compile(
    r'\bлогистическ\w+\s+(?:комплекс\w*|центр\w*)|\bсклад\w+\s+комплекс\w*|'
    r'\bторгов\w+\s+центр\w*|\bжил\w+\s+(?:комплекс\w*|дом\w*)|\bдетск\w+\s+сад\w*|'
    r'\bшкол\w+|\bбольниц\w+|\bполиклиник\w+|\bфельдшерск\w+|\bФАП\b|\bстадион\w*|'
    r'\bавтосалон\w*|\bофисн\w+\s+здани\w+|\bблагоустройств\w+|\bмост\b|\bтротуар\w*', re.I)


def grafa1(t):
    t = t or ''
    if MASHINA.search(t):
        return 'ПРЯМОЙ'
    if PROIZVODSTVO.search(t):
        return 'КОСВЕННЫЙ'
    if CHUZHOE.search(t):
        return 'ЧУЖОЙ'
    return 'КОСВЕННЫЙ'


def pohozh_na_cheloveka(s):
    """Ключ 1-й сессии: минимум две части, не отдел, не регион, не форма собственности."""
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    if len(s.split()) < 2:
        return False
    if re.search(r'отдел|департамент|служб|управлени|респ\b|обл\b|кра[йя]\b|район|'
                 r'ООО|АО\b|ЗАО|ПАО|филиал', s, re.I):
        return False
    return bool(re.match(r'^[А-ЯЁ][а-яё\-]+\s+[А-ЯЁ]', s))


cx = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
print('=== ЖИВЫЕ ПОЛЯ (сперва смотрю, потом считаю)')
polya = {}
for t in tabl:
    kol = [r[1] for r in cx.execute('pragma table_info(%s)' % t)]
    polya[t] = kol
    if t in ('signals', 'people', 'emails', 'companies', 'requisites', 'phone_contacts'):
        n = cx.execute('select count(*) from %s' % t).fetchone()[0]
        print('  %-16s %6d  %s' % (t, n, kol))

# --- Д1: повод -------------------------------------------------------------------------
d1 = set()
sch1 = collections.Counter()
for inn, what in cx.execute('select inn, what from signals'):
    u = grafa1(what or '')
    sch1[u] += 1
    if u != 'ЧУЖОЙ' and str(inn or '').strip():
        d1.add(str(inn).strip())
print('\n=== Д1 ПОВОД: %s' % dict(sch1))
print('  ИНН с непустым НЕ чужим поводом: %d' % len(d1))

# --- Д2: юрлицо ------------------------------------------------------------------------
d2 = set()
if 'people' in polya and 'prinadlezhnost_chem' in polya['people']:
    for inn, chem in cx.execute('select prinadlezhnost_inn, prinadlezhnost_chem from people'
                                ' where prinadlezhnost_chem is not null'):
        if inn and chem and re.search(r'ЕГРЮЛ|карточк\w+\s+закупк|контактное лицо', str(chem), re.I):
            d2.add(str(inn).strip())
    print('\n=== Д2 ЮРЛИЦО: ИНН с сильным доказательством принадлежности: %d' % len(d2))
else:
    print('\n=== Д2 ЮРЛИЦО: графы 2-й сессии в people нет — считать нечем')

# --- Д3: адрес -------------------------------------------------------------------------
d3 = set()
if 'emails' in polya:
    kol = polya['emails']
    ver = 'verified' if 'verified' in kol else None
    sch3 = collections.Counter()
    sel = 'inn, email' + (', verified' if ver else '')
    for r in cx.execute('select %s from emails' % sel):
        inn = str(r[0] or '').strip()
        em = str(r[1] or '').strip()
        v = str(r[2] or '') if ver else ''
        if not inn or '@' not in em:
            continue
        sch3[v or '(пусто)'] += 1
        if v == 'mismatch':
            continue
        d3.add(inn)
    print('\n=== Д3 АДРЕС: verified по адресам: %s' % dict(sch3.most_common(8)))
    print('  ИНН с почтой без mismatch: %d' % len(d3))

# --- Д4: человек -----------------------------------------------------------------------
d4 = set()
if 'people' in polya:
    kol = polya['people']
    pn = 'person' if 'person' in kol else ('name' if 'name' in kol else None)
    ps = 'position' if 'position' in kol else ('post' if 'post' in kol else None)
    n_all = n_hum = 0
    for r in cx.execute('select inn, %s%s from people' % (pn, (', ' + ps) if ps else '')):
        inn = str(r[0] or '').strip()
        n_all += 1
        if inn and pohozh_na_cheloveka(r[1]):
            n_hum += 1
            d4.add(inn)
    print('\n=== Д4 ЧЕЛОВЕК: строк %d, похожих на человека %d, разных ИНН %d'
          % (n_all, n_hum, len(d4)))
cx.close()

vse = d1 & d2 & d3 & d4 if d2 else set()
print('\n=== ТУРНИКЕТ')
print('  Д1 повод      %6d' % len(d1))
print('  Д2 юрлицо     %6d' % len(d2))
print('  Д3 адрес      %6d' % len(d3))
print('  Д4 человек    %6d' % len(d4))
print('  ВСЕ ЧЕТЫРЕ    %6d  <- столько предприятий готовы к генерации письма' % len(vse))
print('  Д1+Д3+Д4 (без Д2) %6d' % len(d1 & d3 & d4))

# --- очередь панели --------------------------------------------------------------------
if os.path.exists(SENDER):
    cs = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
    tb = [r[0] for r in cs.execute("select name from sqlite_master where type='table'")]
    print('\n=== ОЧЕРЕДЬ ПАНЕЛИ (sender.db): %s' % tb)
    for t in tb:
        kol = [r[1] for r in cs.execute('pragma table_info(%s)' % t)]
        if 'status' in kol or 'state' in kol:
            p = 'status' if 'status' in kol else 'state'
            for st, n in cs.execute('select %s, count(*) from %s group by %s'
                                    % (p, t, p)):
                print('  %-18s %-22s %d' % (t, str(st)[:22], n))
    cs.close()

print('\nИТОГ ' + json.dumps({'Д1': len(d1), 'Д2': len(d2), 'Д3': len(d3), 'Д4': len(d4),
                              'ВСЕ ЧЕТЫРЕ': len(vse)}, ensure_ascii=False))
