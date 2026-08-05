# -*- coding: utf-8 -*-
"""Мера повода: показать, НА ЧЁМ она сработала. Особенно на «ЧУЖОЙ» — там цена ошибки.

Мера дала 1 291 ПРЯМОЙ, 3 107 КОСВЕННЫХ, 202 ЧУЖИХ, проба 0 провалов. Но в шести
образцах «ЧУЖОЙ», которые она напечатала, глаза сразу видят чужого среди чужих:

    «На нефтеперерабатывающем заводе введена в эксплуатацию новая установка по
     производству водорода производительностью 25…»                     -> ЧУЖОЙ

Установка производства водорода на НПЗ — это компрессорная техника по определению.
Назвать её «чужой» значит выбросить предприятие с настоящим поводом. Значит мера
зацепилась за что-то в хвосте текста, а хвоста я не видела: печаталось 118 знаков.

ЗАЧЕМ ЭТОТ ПРИБОР. Классификатор, который не называет, ЗА ЧТО он поставил ярлык,
проверить нельзя — можно только поверить. Здесь печатается:
    * ярлык,
    * КАКОЙ кусок текста его вызвал (совпавшая подстрока),
    * `what` ЦЕЛИКОМ, а не первые сто знаков.

Смотрю все 202 ЧУЖИХ подряд — их мало, и каждый из них это потерянное предприятие,
если ярлык неверен. Плюс по 12 случайных из ПРЯМЫХ и КОСВЕННЫХ для равновесия:
проверять только отбракованное — значит искать ошибку одного знака.

Только чтение.
"""
import collections
import json
import os
import random
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\_ops')
BAZA = r'C:\sender\enrich.db'
random.seed(7)  # чтобы выборка повторялась и её можно было перепроверить

MASHINA = re.compile(
    r'компрессор\w*|компрессорн\w+|турбокомпрессор\w*|газодувк\w+|газодувн\w+|'
    r'воздуходувк\w+|нагнетател\w+|бустер\w*|'
    r'воздухоразделен\w+|воздухоразделительн\w+|\bВРУ\b|\bКС\b|\bКСУ\b|'
    r'сжат\w+\s+воздух\w*|сжатого\s+газа|пневмат\w+|пневмосистем\w+|'
    r'осушител\w+\s+возду\w+|осушк\w+\s+возду\w+|'
    r'генератор\w*\s+(?:азота|кислорода)|азотн\w+\s+станци\w+|кислородн\w+\s+станци\w+|'
    r'\bазот\w*\b|\bкислород\w*\b|'
    r'холодильн\w+\s+машин\w+|чиллер\w*|'
    r'ресивер\w*|винтов\w+\s+компрессор\w*|поршнев\w+\s+компрессор\w*|'
    r'центробежн\w+\s+(?:компрессор\w*|машин\w+|нагнетател\w+)', re.I)

CHUZHOE = re.compile(
    r'логистическ\w+\s+(?:комплекс\w*|центр\w*)|склад\w+\s+комплекс\w*|'
    r'торгов\w+\s+центр\w*|бизнес-центр\w*|жил\w+\s+(?:комплекс\w*|дом\w*)|'
    r'детск\w+\s+сад\w*|школ\w+|больниц\w+|поликлиник\w+|стадион\w*|'
    r'автосалон\w*|дилерск\w+\s+центр\w*|седан\w*|кроссовер\w*|'
    r'офисн\w+\s+(?:здани\w+|помещени\w+)|благоустройств\w+|'
    r'дорог\w+|мост\w+|путепровод\w*|тротуар\w*', re.I)


def razbor(t):
    m = MASHINA.search(t or '')
    if m:
        return 'ПРЯМОЙ', m.group(0), m.start()
    c = CHUZHOE.search(t or '')
    if c:
        return 'ЧУЖОЙ', c.group(0), c.start()
    return 'КОСВЕННЫЙ', '', -1


if not os.path.exists(BAZA):
    print('ИТОГ ' + json.dumps({'базы нет': BAZA}, ensure_ascii=False))
    raise SystemExit

cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
stroki = list(cx.execute(
    'select rowid, inn, source, what, sum, source_url from signals'))
cx.close()

po_urovnyu = collections.defaultdict(list)
za_chto = collections.defaultdict(collections.Counter)
for rid, inn, ist, what, summa, url in stroki:
    u, kusok, _ = razbor(what or '')
    po_urovnyu[u].append((rid, inn, ist, what or '', summa, url or ''))
    za_chto[u][kusok.lower()] += 1

print('=== ЗА ЧТО ставится ярлык: какие куски текста срабатывают чаще всего')
for u in ('ПРЯМОЙ', 'ЧУЖОЙ'):
    print('\n  --- %s (всего %d)' % (u, len(po_urovnyu[u])))
    for kusok, n in za_chto[u].most_common(22):
        print('    %5d  «%s»' % (n, kusok[:60]))

print('\n\n########## ВСЕ ЧУЖИЕ ЦЕЛИКОМ — каждый неверный ярлык это потерянное предприятие')
for rid, inn, ist, what, summa, url in po_urovnyu['ЧУЖОЙ']:
    _, kusok, poz = razbor(what)
    print('\n  rowid %-7s ИНН %-12s источник %s' % (rid, inn, str(ist)[:26]))
    print('    ЗАЦЕПИЛОСЬ ЗА: «%s» (позиция %d из %d знаков)' % (kusok, poz, len(what)))
    print('    what: %s' % re.sub(r'\s+', ' ', what))
    if url:
        print('    ссылка: %s' % str(url)[:120])

for u in ('ПРЯМОЙ', 'КОСВЕННЫЙ'):
    vyb = random.sample(po_urovnyu[u], min(12, len(po_urovnyu[u])))
    print('\n\n########## 12 СЛУЧАЙНЫХ «%s» ЦЕЛИКОМ' % u)
    for rid, inn, ist, what, summa, url in vyb:
        _, kusok, _ = razbor(what)
        print('\n  rowid %-7s ИНН %-12s источник %-22s сумма %s'
              % (rid, inn, str(ist)[:22], summa))
        if kusok:
            print('    ЗАЦЕПИЛОСЬ ЗА: «%s»' % kusok)
        print('    what: %s' % re.sub(r'\s+', ' ', what))
        if url:
            print('    ссылка: %s' % str(url)[:120])

print('\n')
print('ИТОГ ' + json.dumps({'всего': len(stroki),
                            'ПРЯМОЙ': len(po_urovnyu['ПРЯМОЙ']),
                            'КОСВЕННЫЙ': len(po_urovnyu['КОСВЕННЫЙ']),
                            'ЧУЖОЙ': len(po_urovnyu['ЧУЖОЙ'])}, ensure_ascii=False))
