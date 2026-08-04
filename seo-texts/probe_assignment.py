# -*- coding: utf-8 -*-
"""Что сейчас в company_assignment: смотрим ДО того, как перезаписывать чужую очередь.

Правило простое: прежде чем менять поле, по которому работает живой человек, надо знать его
нынешний вид — диапазон, распределение, кому принадлежат строки. Иначе «улучшение» может
незаметно перевернуть порядок у продавца посреди смены.
"""
import json
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
o = {}
o['строк'] = cx.execute('select count(*) from company_assignment').fetchone()[0]
o['по_пользователям'] = dict(cx.execute(
    'select coalesce(username,\'(нет)\'), count(*) from company_assignment '
    'group by 1 order by 2 desc').fetchall())
o['диапазон_score'] = cx.execute(
    'select min(assignment_score), max(assignment_score), avg(assignment_score) '
    'from company_assignment').fetchone()
o['ступени_score'] = cx.execute(
    'select cast(coalesce(assignment_score,0) as int)/10*10, count(*) '
    'from company_assignment group by 1 order by 1 desc limit 12').fetchall()
o['примеры'] = cx.execute(
    'select inn, username, assignment_score, has_phone, has_tech, has_purchaser, '
    'assigned_at, assigned_by from company_assignment order by assignment_score desc limit 6'
).fetchall()
o['с_телефоном_по_флагу'] = cx.execute(
    'select coalesce(has_phone,0), count(*) from company_assignment group by 1').fetchall()
print(json.dumps(o, ensure_ascii=False, indent=1))
