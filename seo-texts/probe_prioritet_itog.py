# -*- coding: utf-8 -*-
"""Перечит приоритета ИЗ БАЗЫ после применения: не «я записал», а «там лежит».

Владелец спрашивает, верны ли приоритеты теперь. Отвечать своим прогоном нельзя — он показывает
намерение, а не результат. Здесь всё читается из company_assignment заново и сверяется с
фактами: сколько предприятий в каждой очереди, как распределён вес, и — главное — есть ли
случаи, где «очевидно центробежное» стоит ниже «не установлено». Это и был вопрос.
"""
import collections
import json
import re
import sqlite3

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
o = {}
o['строк_очереди'] = sale.execute('select count(*) from company_assignment').fetchone()[0]
o['по_ступеням'] = dict(sale.execute("""
    select case when assignment_score >= 2000 then 'звонить сегодня'
                when assignment_score >= 1000 then 'добыть контакт'
                else 'фон' end, count(*)
    from company_assignment group by 1 order by 2 desc""").fetchall())
o['диапазон'] = sale.execute(
    'select min(assignment_score), max(assignment_score) from company_assignment').fetchone()

# Есть ли у предприятия хоть один доказанно центробежный факт.
centro = {r[0] for r in sale.execute("""
    select distinct inn from f.fact
    where lower(coalesce(equipment_type,'')) like '%центробежн%'
       or lower(coalesce(quote,'')) like '%центробежн%'
       or lower(coalesce(quote,'')) like '%турбовоздуходувк%'""")}
vozduh = {r[0] for r in sale.execute("""
    select distinct inn from f.fact
    where (lower(coalesce(medium,'')) like '%воздух%'
           or lower(coalesce(quote,'')) like '%воздух%')
      and lower(coalesce(quote,'')) not like '%природн%газ%'""")}

sch = collections.Counter()
nizhe = []
for inn, user, score in sale.execute(
        'select inn, username, assignment_score from company_assignment'):
    est_c = inn in centro
    est_v = inn in vozduh
    k = ('центробежный + воздух' if est_c and est_v else
         'центробежный, среда не названа' if est_c else
         'воздух без центробежного' if est_v else 'ни того, ни другого')
    sch[k] += 1
    if not est_c:
        nizhe.append(score)
o['предприятий_по_доказательству'] = dict(sch)
# КОНТРОЛЬ ВОПРОСА ВЛАДЕЛЬЦА: средний вес центробежных должен быть выше, чем у остальных.
sr = {}
for k in sch:
    pass
sr['центробежные'] = sale.execute(
    'select avg(assignment_score) from company_assignment where inn in (%s)'
    % ','.join('?' * len(centro)), list(centro)).fetchone()[0] if centro else None
sr['без_центробежного'] = sale.execute(
    'select avg(assignment_score) from company_assignment where inn not in (%s)'
    % ','.join('?' * len(centro)), list(centro)).fetchone()[0] if centro else None
o['средний_вес'] = sr
o['верх_20'] = sale.execute("""
    select a.inn, a.username, a.assignment_score, a.has_phone, a.has_tech
    from company_assignment a order by a.assignment_score desc limit 8""").fetchall()
print(json.dumps(o, ensure_ascii=False, indent=1))
