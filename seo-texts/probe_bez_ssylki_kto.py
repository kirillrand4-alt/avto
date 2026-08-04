# -*- coding: utf-8 -*-
"""Кто именно теряет ссылку: 1 525 контактов без адреса первоисточника.

Прошлый разрез печатал верх по ЧИСЛУ контактов, а нужен верх по числу ПОТЕРЬ — это разные
списки. Заодно смотрю, восстановима ли ссылка: у Тендер.Про карточка компании собирается по
company_id, а у предприятия почти всегда есть факты со ссылками, откуда виден первоисточник.
"""
import json
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
o = {}
o['без_ссылки_всего'] = cx.execute(
    "select count(*) from person where coalesce(source_url,'')=''").fetchone()[0]
o['виновники'] = cx.execute("""
    select coalesce(source,'(пусто)'), count(*) from person
    where coalesce(source_url,'')='' group by 1 order by 2 desc limit 12""").fetchall()
o['без_ссылки_и_без_источника'] = cx.execute(
    "select count(*) from person where coalesce(source_url,'')='' "
    "and coalesce(source,'')=''").fetchone()[0]
# Восстановимость: есть ли у предприятия факт со ссылкой на ту же площадку.
o['ИНН_без_ссылки'] = cx.execute(
    "select count(distinct inn) from person where coalesce(source_url,'')=''").fetchone()[0]
o['из_них_есть_факт_со_ссылкой'] = cx.execute("""
    select count(distinct p.inn) from person p
    where coalesce(p.source_url,'')=''
      and exists (select 1 from fact f where f.inn = p.inn
                    and coalesce(f.source_url,'') <> '')""").fetchone()[0]
o['восстановимо_через_тендерпро'] = cx.execute("""
    select count(*) from person p
    where coalesce(p.source_url,'')=''
      and lower(coalesce(p.source,'')) like '%tender%'
      and exists (select 1 from fact f where f.inn = p.inn
                    and lower(coalesce(f.source_url,'')) like '%tender.pro%')""").fetchone()[0]
print(json.dumps(o, ensure_ascii=False, indent=1))
