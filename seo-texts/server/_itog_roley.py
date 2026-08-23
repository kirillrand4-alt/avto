# -*- coding: utf-8 -*-
r"""Чем кончился прогон подписей: лог, что записано, сколько ролей."""
import json
import os
import sqlite3

d = {}
лог = r'C:\sender\server\roli_telefonov.log'
if os.path.exists(лог):
    строки = [s.strip() for s in open(лог, encoding='utf-8', errors='replace')
              if s.strip()]
    d['лог_хвост'] = [s[:190] for s in строки[-6:]]
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
d['строк_от_подписи'] = c.execute(
    "select count(*) from phone_contacts where source like '%подпись со страницы%'"
).fetchone()[0]
d['из_них_с_ролью'] = c.execute(
    "select count(*) from phone_contacts where source like '%подпись со страницы%' "
    "and coalesce(role,'') not in ('','общий')").fetchone()[0]
d['компаний_затронуто'] = c.execute(
    "select count(distinct inn) from phone_contacts "
    "where source like '%подпись со страницы%'").fetchone()[0]
d['всего_в_phone_contacts'] = c.execute(
    'select count(*) from phone_contacts').fetchone()[0]
d['всего_с_ролью'] = c.execute(
    "select count(*) from phone_contacts where coalesce(role,'') "
    "not in ('','общий')").fetchone()[0]
d['стадия_пройдена_компаний'] = c.execute(
    "select count(*) from stage_log where stage='phone_podpis'").fetchone()[0]
d['роли'] = {r[0]: r[1] for r in c.execute(
    "select role, count(*) k from phone_contacts where "
    "source like '%подпись со страницы%' and coalesce(role,'') not in ('','общий') "
    'group by role order by k desc limit 10')}
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1))
