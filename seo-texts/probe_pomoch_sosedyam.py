# -*- coding: utf-8 -*-
"""Чем я реально могу закрыть затыки соседей — проверяю по базе, а не обещаю.

ИХ ЗАТЫКИ, названные в журналах:
  2-я сессия: (а) РТС требует слаг ИНН-КПП, а КПП не знает ни справочник Сбербанк-АСТ, ни
              ЕГРЮЛ — 23 предприятия стоят; (б) должности нет ни на одной площадке, роль
              поставить нечем.
  1-я сессия: (в) hh не листается дальше второй сотни.

Смотрю: есть ли КПП где-нибудь в наших базах, и чем У МЕНЯ ставится признак технической роли —
чтобы отдать приём, а не пересказ.
"""
import collections
import json
import re
import sqlite3

o = {}
for imya, put in (('centrifugal', r'C:\seostat\data\centrifugal.db'),
                  ('enrich', r'C:\sender\enrich.db')):
    try:
        cx = sqlite3.connect(put)
        polya = []
        for (t,) in cx.execute("select name from sqlite_master where type='table'"):
            for r in cx.execute(f'pragma table_info("{t}")'):
                if re.search(r'kpp|кпп', r[1], re.I):
                    n = cx.execute(f'select count(*) from "{t}" where coalesce("{r[1]}",\'\') <> \'\''
                                   ).fetchone()[0]
                    polya.append([t, r[1], n])
        o[f'{imya}: поля с КПП'] = polya or 'нет ни одного'
    except Exception as e:  # noqa: BLE001
        o[imya] = f'{type(e).__name__}: {str(e)[:60]}'

# Чем ставится техническая роль у меня — распределение должностей с is_tech.
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
o['людей_всего'] = cx.execute('select count(*) from person').fetchone()[0]
o['с_признаком_is_tech'] = cx.execute(
    'select count(*) from person where coalesce(is_tech,0)=1').fetchone()[0]
o['должности_техЛПР_топ'] = cx.execute(
    "select coalesce(position,'(пусто)'), count(*) from person where coalesce(is_tech,0)=1 "
    "group by 1 order by 2 desc limit 12").fetchall()
o['роли_топ'] = cx.execute(
    "select coalesce(role,'(пусто)'), count(*) from person where coalesce(role,'') <> '' "
    "group by 1 order by 2 desc limit 12").fetchall()
o['техЛПР_без_должности'] = cx.execute(
    "select count(*) from person where coalesce(is_tech,0)=1 and coalesce(position,'')=''"
).fetchone()[0]
print(json.dumps(o, ensure_ascii=False, indent=1))
