# -*- coding: utf-8 -*-
"""Кто считает приоритет и что даст его понижение — цифрами, до того как просить соседей.

ВОПРОС ВЛАДЕЛЬЦА: «кто занимается приоритетом?» и «лучше бы приоритет у них понизить, и у тех
у кого номеров нету тоже». Отвечать надо не догадкой, а тем, что в базе: смотрю, какие поля
приоритета есть, чем они заполнены и сколько компаний тронет каждое из двух понижений.

ПОЧЕМУ ПОНИЖЕНИЕ ЛУЧШЕ СКРЫТИЯ — это и есть суть указания. Скрытая компания исчезает из
очереди целиком, и вернуть её может только тот, кто помнит, что скрывал. Опущенная в
приоритете остаётся видимой, просто ниже: продавец до неё дойдёт, когда кончатся сильные, а
данные по ней продолжают копиться. Ровно правило владельца «разделять, а не отсеивать».
"""
import json
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
o = {}
kol = [r[1] for r in cx.execute('pragma table_info(company)')]
o['поля_приоритета'] = [k for k in kol if 'prioritet' in k or 'vazhnost' in k]
o['компаний_всего'] = cx.execute('select count(*) from company').fetchone()[0]
o['распределение_vazhnost'] = cx.execute(
    'select cast(coalesce(vazhnost_pokupki,0) as int)/25*25, count(*) from company '
    'group by 1 order by 1 desc').fetchall()
o['примеры_prioritet_pochemu'] = cx.execute(
    "select coalesce(prioritet_pochemu,''), count(*) from company "
    "where coalesce(prioritet_pochemu,'') <> '' group by 1 order by 2 desc limit 5").fetchall()

# Понижение 1: возвращённые из партии «марка не совпала».
sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
o['ещё_скрыто_company'] = sale.execute(
    "select count(distinct inn) from hidden_item where kind='company'").fetchone()[0]
o['видно_сейчас'] = o['компаний_всего'] - o['ещё_скрыто_company']

# Понижение 2: нет ни одного телефона.
o['видимых_без_единого_телефона'] = cx.execute("""
    select count(*) from company c
    where not exists (select 1 from person p
                      where p.inn = c.inn and coalesce(p.phone,'') <> '')""").fetchone()[0]
o['видимых_с_телефоном'] = o['компаний_всего'] - o['видимых_без_единого_телефона']
o['с_телефоном_и_ролью'] = cx.execute("""
    select count(distinct p.inn) from person p
    where coalesce(p.phone,'') <> '' and coalesce(p.is_tech,0) = 1""").fetchone()[0]
# Сколько из видимых с высокой важностью не имеют телефона — это и есть верх очереди впустую.
o['важность_75plus_без_телефона'] = cx.execute("""
    select count(*) from company c
    where coalesce(c.vazhnost_pokupki,0) >= 75
      and not exists (select 1 from person p
                      where p.inn = c.inn and coalesce(p.phone,'') <> '')""").fetchone()[0]
o['важность_75plus_всего'] = cx.execute(
    'select count(*) from company where coalesce(vazhnost_pokupki,0) >= 75').fetchone()[0]
print(json.dumps(o, ensure_ascii=False, indent=1))
