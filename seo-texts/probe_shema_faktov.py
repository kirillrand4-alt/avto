# -*- coding: utf-8 -*-
"""Схема panel-базы: имена колонок берутся из базы, а не из памяти.

ПОВОД. Запрос к `fact.text` упал с «no such column». Угадывать имена дальше — тот же
способ записать ложный ноль, что и раньше: неверная колонка даёт либо падение (видно), либо
пустоту (не видно). Печатаю схему целиком один раз.
"""
import json
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
out = {}
for (t,) in cx.execute("select name from sqlite_master where type='table' order by name"):
    kol = [r[1] for r in cx.execute(f'pragma table_info("{t}")')]
    n = cx.execute(f'select count(*) from "{t}"').fetchone()[0]
    out[t] = {'строк': n, 'колонки': kol}
print(json.dumps(out, ensure_ascii=False, indent=1))
print('--- пример строки fact ---')
try:
    r = cx.execute('select * from fact limit 1').fetchone()
    print(json.dumps([str(x)[:120] for x in r], ensure_ascii=False))
except Exception as e:
    print('нет:', e)
