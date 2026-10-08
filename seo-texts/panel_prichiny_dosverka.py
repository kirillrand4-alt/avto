# -*- coding: utf-8 -*-
"""Досверка после проверки причин: рабочая база продавцов без следов теста, временный файл убран."""
import os, sqlite3, tempfile
rab = r'C:\centro2\data\centro_sales_meyer1.db'
c = sqlite3.connect(rab)
print('рабочая база: статусов %d, комментариев %d, журнал %d' % tuple(
    c.execute('select count(*) from %s' % t).fetchone()[0] for t in ('company_state', 'company_comment', 'activity_log')))
print('следов теста («звонил гл. инженеру»): %d' % c.execute(
    "select count(*) from company_comment where body like '%звонил гл. инженеру%'").fetchone()[0])
v = os.path.join(tempfile.gettempdir(), 'proverka_prichin.db')
if os.path.exists(v):
    os.remove(v)
print('временный файл: %s' % ('убран' if not os.path.exists(v) else 'ОСТАЛСЯ'))
