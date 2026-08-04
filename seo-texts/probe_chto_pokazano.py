# -*- coding: utf-8 -*-
"""Что панель ПОКАЗЫВАЕТ как приоритет и чем она СОРТИРУЕТ — это может быть разное.

ПОВОД. На карточке владельца стоит «Приоритет 750.0». Моя шкала после применения — от 0.2 до
2055.2 со ступенями (2000 звонить сегодня, 1000 добыть контакт, 0 фон). 750 в неё не
укладывается вовсе. Значит либо панель показывает ДРУГОЕ поле, либо моя запись не доехала.
Разница важна: продавец видит число, которое, возможно, не имеет отношения к порядку его же
очереди.

Проверяю по конкретному ИНН с карточки (1500004950): что лежит в каждом поле приоритета, и
совпадает ли показанное с тем, чем сортируется очередь.
"""
import json
import sqlite3

INN = '1500004950'
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
o = {}
kol = [r[1] for r in cx.execute('pragma table_info(company)')]
polya = [k for k in kol if 'prioritet' in k or 'vazhnost' in k or 'ball' in k]
o['поля_приоритета_в_company'] = polya
r = cx.execute(f'select {",".join(polya)} from company where inn = ?', (INN,)).fetchone()
o['значения_у_этого_ИНН'] = dict(zip(polya, r)) if r else 'ИНН не найден'
o['assignment_score'] = sale.execute(
    'select username, assignment_score from company_assignment where inn = ?', (INN,)).fetchall()

# Сколько компаний видит панель после фильтра скрытых, по пользователям.
o['строк_очереди_по_пользователям'] = dict(sale.execute(
    'select username, count(*) from company_assignment group by 1').fetchall())
skryto = {x[0] for x in sale.execute("select inn from hidden_item where kind='company'")}
for u in ('user1', 'user2'):
    inn_u = {x[0] for x in sale.execute(
        'select inn from company_assignment where username = ?', (u,))}
    o[f'{u}: в очереди'] = len(inn_u)
    o[f'{u}: минус скрытые'] = len(inn_u - skryto)
o['скрытий_company_всего'] = len(skryto)

# Диапазоны обеих шкал — чтобы видеть, какая из них похожа на показанную.
for p in polya:
    o[f'диапазон_{p}'] = cx.execute(
        f'select min("{p}"), max("{p}") from company where "{p}" is not null').fetchone()
o['диапазон_assignment_score'] = sale.execute(
    'select min(assignment_score), max(assignment_score) from company_assignment').fetchone()
print(json.dumps(o, ensure_ascii=False, indent=1))
