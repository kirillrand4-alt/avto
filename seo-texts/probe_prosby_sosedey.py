# -*- coding: utf-8 -*-
"""Три просьбы соседей, которые проверяются по базе, а не рассуждением.

1. 1-я сессия: пересечь мои 542 предприятия очереди «добыть контакт» с их 180 ИНН, у которых
   появились ИМЕНА. Где есть и повод, и имя — там обратный ход даст максимум.
2. 2-я сессия: есть ли у нас дата регистрации юрлица. Без неё нельзя проверить «факт СТАРШЕ
   компании», а это вскрывает неверно привязанные ИНН.
3. 2-я сессия: 754 факта, где метка «центробежная» стоит вместе с признаком ЧУЖОЙ машины.
   Смотрю, сколько из них уже свёрнуто моей разметкой, а сколько ещё висит.
"""
import collections
import json
import re
import sqlite3

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
o = {}

# 1. Очередь «добыть контакт» — это ступень 1000..1999.
dobyt = {r[0] for r in sale.execute(
    'select distinct inn from company_assignment '
    'where assignment_score >= 1000 and assignment_score < 2000')}
o['очередь_добыть_контакт'] = len(dobyt)
# Предприятия, где ИМЯ технического человека уже есть, а телефона нет.
s_imenem_bez_tel = {r[0] for r in sale.execute("""
    select distinct inn from f.person
    where coalesce(person,'') <> '' and coalesce(phone,'') = '' and coalesce(is_tech,0) = 1""")}
o['есть_имя_техЛПР_без_телефона'] = len(s_imenem_bez_tel)
o['ПЕРЕСЕЧЕНИЕ_гнать_первыми'] = len(dobyt & s_imenem_bez_tel)

# 2. Дата регистрации юрлица — есть ли поле вообще.
# pragma не понимает префикс присоединённой базы через точку — нужен свой коннект.
cx2 = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
kol = [r[1] for r in cx2.execute('pragma table_info(company)')]
daty = [k for k in kol if 'date' in k.lower() or 'dat' in k.lower() or 'reg' in k.lower()]
o['поля_похожие_на_дату'] = daty
for k in daty:
    o[f'заполнено_{k}'] = cx2.execute(
        f'select count(*) from company where coalesce("{k}",\'\') <> \'\'').fetchone()[0]

# 3. «центробежная» вместе с признаком чужой машины — и сколько из них уже свёрнуто.
CHUZHOE = re.compile(r'вентилятор|дымосос|поршнев|винтов|Рутс|\bАВО\b|\bнасос', re.I)
svernuto = {r[0] for r in sale.execute("select value from hidden_item where kind='fact'")}
vsego = visit = 0
for fid, tip, quote in sale.execute(
        "select id, coalesce(equipment_type,''), coalesce(quote,'') from f.fact"):
    if 'центробежн' not in tip.lower():
        continue
    if not CHUZHOE.search(quote):
        continue
    vsego += 1
    if str(fid) not in svernuto:
        visit += 1
o['метка_центробежная_при_чужой_машине'] = vsego
o['из_них_ЕЩЁ_НЕ_свёрнуто'] = visit
print(json.dumps(o, ensure_ascii=False, indent=1))
